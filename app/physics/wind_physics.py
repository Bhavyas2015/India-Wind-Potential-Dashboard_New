import numpy as np
from scipy.special import gamma as gf
from typing import List, Dict, Optional
import warnings
warnings.filterwarnings('ignore')

TURBINES = {
    'micro_1kw':   {'label':'Micro 1kW','ci':2.0,'rated':10.0,'co':20.0,'capKW':1,'hub':15,'rotor':1.8,'capex_cr_mw':0.8,'curve':[0,0,0.02,0.05,0.12,0.25,0.45,0.65,0.82,0.95,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0]},
    'bergey_10kw': {'label':'Bergey Excel 10kW','ci':2.5,'rated':11.0,'co':25.0,'capKW':10,'hub':24,'rotor':7,'capex_cr_mw':1.2,'curve':[0,0,0,0.2,0.7,1.7,3.2,5.2,7.2,9,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,0]},
    'enair_30kw':  {'label':'Enair E30 30kW','ci':3.0,'rated':12.0,'co':25.0,'capKW':30,'hub':30,'rotor':9,'capex_cr_mw':1.5,'curve':[0,0,0,0.5,2,5,10,18,25,29,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,0]},
    'enercon_e33': {'label':'Enercon E33 330kW','ci':2.0,'rated':12.0,'co':28.0,'capKW':330,'hub':50,'rotor':33,'capex_cr_mw':4.8,'curve':[0,0,0,4,14,35,80,145,220,285,318,330,330,330,330,330,330,330,330,330,330,330,330,330,330,330]},
    'suzlon_s64':  {'label':'Suzlon S64 2.1MW','ci':3.0,'rated':14.0,'co':25.0,'capKW':2100,'hub':90,'rotor':64,'capex_cr_mw':5.5,'curve':[0,0,0,20,80,220,520,950,1500,1900,2050,2100,2100,2100,2100,2100,2100,2100,2100,2100,2100,2100,2100,2100,2100,0]},
    'vestas_v90':  {'label':'Vestas V90 2MW','ci':3.5,'rated':13.0,'co':25.0,'capKW':2000,'hub':80,'rotor':90,'capex_cr_mw':5.8,'curve':[0,0,0,0,35,135,330,620,1000,1400,1750,1950,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,2000,0]},
    'siemens_sg5': {'label':'Siemens SG5 5MW','ci':3.0,'rated':13.0,'co':25.0,'capKW':5000,'hub':130,'rotor':132,'capex_cr_mw':6.2,'curve':[0,0,0,30,120,350,900,1800,3000,4000,4700,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,5000,0]},
    'ge_haliade':  {'label':'GE Haliade-X 15MW','ci':3.0,'rated':13.0,'co':25.0,'capKW':15000,'hub':150,'rotor':220,'capex_cr_mw':8.0,'curve':[0,0,0,100,350,900,2100,4000,6500,9500,12500,14500,15000,15000,15000,15000,15000,15000,15000,15000,15000,15000,15000,15000,15000,0]},
}

def power_law(v, h, h0=10.0, a=0.143):
    return float(v * (h / h0) ** a) if v > 0 and h > 0 else 0.0

def air_density(T_c, P_hPa=1013.25):
    return float((P_hPa * 100) / (287.058 * (T_c + 273.15)))

def alt_pressure(elev):
    return 101325.0 * (1.0 - 2.25577e-5 * elev) ** 5.25588

def fit_weibull(ws):
    vs = np.array([v for v in ws if v > 0.1], dtype=np.float64)
    n = len(vs)
    if n < 6:
        mv = float(np.mean(vs)) if n > 0 else 5.0
        return {'k': 2.0, 'c': mv * 1.128, 'r2': 0.0, 'mean_ws': mv, 'n': n, 'ok': False}
    k = float(np.clip((np.std(vs) / np.mean(vs)) ** -1.086, 0.5, 10.0))
    ln_v = np.log(vs)
    for _ in range(60):
        vk = vs ** k
        vkl = vk * ln_v
        s = np.sum(vk)
        sl = np.sum(vkl)
        sl2 = np.sum(vk * ln_v ** 2)
        f = (1 / k) + np.mean(ln_v) - (sl / s)
        df = (-1 / k ** 2) - ((s * sl2 - sl ** 2) / s ** 2)
        if abs(df) < 1e-14:
            break
        kn = float(np.clip(k - f / df, 0.5, 10.0))
        if abs(kn - k) < 1e-7:
            k = kn
            break
        k = kn
    c = float((np.sum(vs ** k) / n) ** (1 / k))
    sv = np.sort(vs)
    ec = (np.arange(1, n + 1) - 0.5) / n
    tc = 1 - np.exp(-(sv / c) ** k)
    r2 = float(np.clip(1 - np.sum((ec - tc) ** 2) / (np.sum((ec - np.mean(ec)) ** 2) + 1e-12), 0, 1))
    return {'k': round(k, 4), 'c': round(c, 4), 'r2': round(r2, 4), 'mean_ws': round(float(c * gf(1 + 1 / k)), 4), 'n': n, 'ok': True}

def wpdf(v, k, c):
    v = np.asarray(v, dtype=np.float64)
    out = np.zeros_like(v)
    m = v > 0
    vc = v[m] / c
    out[m] = (k / c) * (vc ** (k - 1)) * np.exp(-(vc ** k))
    return out

def wpd(k, c, rho=1.225):
    return float(0.5 * rho * c ** 3 * gf(1 + 3 / k))

def cap_factor(k, c, tkey, dv=0.1):
    if tkey not in TURBINES:
        return 0.0
    t = TURBINES[tkey]
    cu = t['curve']
    cap = t['capKW']
    va = np.arange(0, 35 + dv, dv)
    pa = wpdf(va, k, c)
    def pw(v):
        if v < t['ci'] or v >= t['co']:
            return 0.0
        i = min(int(v), len(cu) - 2)
        f = v - i
        return cu[i] * (1 - f) + cu[min(i + 1, len(cu) - 1)] * f
    return float(np.clip(np.trapz([pw(v) for v in va] * pa, va) / cap, 0, 0.65))

def aep(cf, cap_kw):
    return float(cf * cap_kw * 8760 / 1000)

def iec_class(ws):
    if ws >= 10: return 'IEC-I'
    if ws >= 8.5: return 'IEC-II'
    if ws >= 7.5: return 'IEC-III'
    return 'IEC-S'

def nrel_class(w):
    for thr, lb in [(800, '7'), (400, '6'), (250, '5'), (200, '4'), (150, '3'), (100, '2')]:
        if w > thr:
            return 'NREL-' + lb
    return 'NREL-1'

def uncertainty(ws_arr, r2, n_yrs=1):
    a = np.array([v for v in ws_arr if v > 0.1])
    if len(a) < 12:
        return {'ws_pct': 15.0, 'aep_pct': 20.0, 'p90': 0.74}
    cov = np.std(a) / np.mean(a) * 100
    ws_p = float(np.clip(cov + 3 + (1 - r2) * 8 + max(0, 5 - n_yrs), 3, 30))
    aep_p = float(np.clip(ws_p * 1.3 + 2, 5, 35))
    return {'ws_pct': round(ws_p, 2), 'aep_pct': round(aep_p, 2), 'p90': round(max(0.5, 1 - 1.28 * aep_p / 100), 3)}

def build_point(lat, lon, ws10, t2m, hub, alpha, tkey, src, elev=0.0, wd10=None):
    ws = np.array([v for v in ws10 if v > 0.1])
    tm = np.array([t for t in t2m if t > -90])
    n_mo = len(ws)
    n_yr = max(1, n_mo // 12)
    wh = np.array([power_law(v, hub, 10.0, alpha) for v in ws])
    T = float(np.mean(tm)) if len(tm) > 0 else 25.0
    rho = air_density(T, alt_pressure(elev) / 100)
    wb = fit_weibull(wh.tolist())
    wp = wpd(wb['k'], wb['c'], rho)
    cf = cap_factor(wb['k'], wb['c'], tkey)
    cap = TURBINES[tkey]['capKW']
    ae = aep(cf, cap)
    unc = uncertainty(wh.tolist(), wb['r2'], n_yr)
    mm = [round(float(np.mean(wh[m::12])), 3) if len(wh[m::12]) > 0 else 0.0 for m in range(12)]
    mwd = round(float(np.mean(wd10)), 1) if wd10 and len(wd10) > 0 else 225.0
    return {
        'lat': round(lat, 4), 'lon': round(lon, 4),
        'meanWS': round(wb['mean_ws'], 3), 'wpd': round(wp, 1),
        'wb': wb, 'cf': round(cf, 4), 'aep': round(ae, 2),
        'rho': round(rho, 4), 'mean_T': round(T, 1),
        'unc': unc, 'monthlyMeans': mm,
        'iec_cls': iec_class(wb['mean_ws']), 'nrel_cls': nrel_class(wp),
        'wsHub': wh.tolist(), 'ws10': ws.tolist(),
        'meanWD': mwd, 'dataSource': src, 'elev_m': elev, 'n_months': n_mo,
    }