import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple

RI = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32}


def ahp_weights(raw: Dict[str, float]) -> Tuple[Dict[str, float], float, bool]:
    keys = list(raw.keys())
    n = len(keys)
    mat = [[0.0] * n for _ in range(n)]
    for i, ki in enumerate(keys):
        for j, kj in enumerate(keys):
            a, b = raw[ki], raw[kj]
            mat[i][j] = a / b if a >= b else 1.0 / (b / a)
    col_sums = [sum(mat[i][j] for i in range(n)) for j in range(n)]
    norm = [[mat[i][j] / col_sums[j] for j in range(n)] for i in range(n)]
    w = [sum(norm[i]) / n for i in range(n)]
    wv = [sum(mat[i][j] * w[j] for j in range(n)) for i in range(n)]
    lmax = sum(wv[i] / w[i] for i in range(n)) / n
    ci = (lmax - n) / (n - 1) if n > 1 else 0
    ri = RI.get(n, 1.12)
    cr = ci / ri if ri > 0 else 0
    return {k: round(w[i], 4) for i, k in enumerate(keys)}, round(cr, 4), cr < 0.1


@dataclass
class MCDAConstraints:
    max_slope:   float = 15.0
    buffer_m:    float = 500.0
    max_grid_km: float = 30.0
    min_wind_ms: float = 4.0
    excl_forest: bool = True
    excl_water:  bool = True
    excl_prot:   bool = True


SUIT_CLS = [
    (0.70, 1.00, 'High', '#00d084'),
    (0.45, 0.70, 'Moderate', '#52c974'),
    (0.20, 0.45, 'Low', '#ffb800'),
    (0.00, 0.20, 'Marginal', '#4a6278')
]


def suit_cls(s):
    if s < 0:
        return 'Excluded', '#ff3d57'
    for lo, hi, lb, co in SUIT_CLS:
        if lo <= s <= hi:
            return lb, co
    return 'Marginal', '#4a6278'


def _mmn(v):
    mn, mx = np.nanmin(v), np.nanmax(v)
    if mx - mn < 1e-9:
        return np.full_like(v, 0.5)
    return (v - mn) / (mx - mn)


class MCDAEngine:
    def __init__(self, raw_weights=None, constraints=None):
        rw = raw_weights or {'wind': 5, 'land': 4, 'ter': 3, 'acc': 4, 'fin': 3}
        self.ahp_w, self.cr, self.cr_ok = ahp_weights(rw)
        self.c = constraints or MCDAConstraints()

    def _excl(self, pt):
        c = self.c
        lu = pt.get('lulc', 'unknown')
        if pt.get('slope', 0) > c.max_slope:
            return 'slope>{}'.format(c.max_slope)
        if lu == 'urban':
            return 'urban'
        if lu == 'water' and c.excl_water:
            return 'water'
        if lu == 'forest' and c.excl_forest:
            return 'forest'
        if lu == 'protected' and c.excl_prot:
            return 'protected'
        if pt.get('nearSettle') and c.buffer_m > 300:
            return 'settlement_buffer'
        if pt.get('gridDist', 0) > c.max_grid_km:
            return 'grid_far'
        if pt.get('meanWS', 0) < c.min_wind_ms:
            return 'low_wind'
        return None

    def score(self, pts):
        if not pts:
            return []
        excl = [self._excl(p) for p in pts]
        vi = [i for i, e in enumerate(excl) if e is None]
        if not vi:
            return [{'s': -1, 'cls': 'Excluded', 'col': '#ff3d57', 'excl': excl[i], 'wf': 0, 'lf': 0, 'tf': 0, 'af': 0} for i in range(len(pts))]
        vp = [pts[i] for i in vi]
        wpd_arr = np.array([p.get('wpd', 0) for p in vp])
        sl = np.array([p.get('slope', 0) for p in vp])
        el = np.array([p.get('elev_m', 0) for p in vp])
        lu_map = {'open': 1.0, 'agricultural': 0.85, 'shrubland': 0.75, 'forest': 0.2, 'wetland': 0.1, 'unknown': 0.5}
        lu = np.array([lu_map.get(p.get('lulc', 'unknown'), 0.5) for p in vp])
        gd = np.array([p.get('gridDist', 30) for p in vp])
        lc = np.array([p.get('lcoe_inr_kwh') or 5.0 for p in vp])
        wf = _mmn(wpd_arr)
        ms = max(self.c.max_slope, 1)
        tf = np.clip(1 - sl / (ms * 2), 0, 1) * np.where(el > 700, 0.5, 1.0)
        lf = lu
        af = _mmn(-gd)
        ff = _mmn(-lc)
        w = self.ahp_w
        sc = np.clip(
            wf * w.get('wind', 0.35) +
            tf * w.get('ter', 0.20) +
            lf * w.get('land', 0.20) +
            af * w.get('acc', 0.15) +
            ff * w.get('fin', 0.10), 0, 1)
        rm = {}
        for j, i in enumerate(vi):
            s = float(sc[j])
            cl, co = suit_cls(s)
            rm[i] = {'s': round(s, 4), 'cls': cl, 'col': co, 'excl': None,
                     'wf': round(float(wf[j]), 4), 'tf': round(float(tf[j]), 4),
                     'lf': round(float(lf[j]), 4), 'af': round(float(af[j]), 4)}
        out = []
        for i in range(len(pts)):
            if i in rm:
                out.append(rm[i])
            else:
                cl, co = suit_cls(-1)
                out.append({'s': -1, 'cls': 'Excl({})'.format(excl[i]), 'col': co, 'excl': excl[i], 'wf': 0, 'lf': 0, 'tf': 0, 'af': 0})
        return out

    def summary(self, pts, scores, gs=0.5):
        ck2 = (gs * 111) ** 2
        vld = [(p, s) for p, s in zip(pts, scores) if s['s'] >= 0]
        hi = [(p, s) for p, s in zip(pts, scores) if s['s'] > 0.70]
        ex = [s for s in scores if s['s'] < 0]
        if not vld:
            return {'error': 'no valid points'}
        return {
            'n_total': len(pts), 'n_valid': len(vld),
            'n_high': len(hi), 'n_excl': len(ex),
            'pct_high': round(len(hi) / max(1, len(pts)) * 100, 1),
            'high_km2': round(len(hi) * ck2, 1),
            'mean_ws': round(float(np.mean([p['meanWS'] for p, _ in vld])), 3),
            'mean_wpd': round(float(np.mean([p['wpd'] for p, _ in vld])), 1),
            'mean_cf': round(float(np.mean([p['cf'] for p, _ in vld])), 4),
            'mean_aep': round(float(np.mean([p['aep'] for p, _ in vld])), 2),
            'wb_k': round(float(np.mean([p['wb']['k'] for p, _ in vld])), 4),
            'wb_c': round(float(np.mean([p['wb']['c'] for p, _ in vld])), 4),
            'ahp_cr': round(self.cr, 4), 'ahp_cr_ok': self.cr_ok,
        }