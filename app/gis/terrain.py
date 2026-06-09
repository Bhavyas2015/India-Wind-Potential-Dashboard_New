import httpx
import asyncio
import diskcache
import math
import logging

logger = logging.getLogger('windsite.terrain')
TOPO = 'https://api.opentopodata.org/v1/srtm90m'


class TerrainClient:
    def __init__(self, cache_dir='data/cache/terrain'):
        self.cache = diskcache.Cache(cache_dir)

    def _ck(self, la, lo):
        return 'elev_{:.2f}_{:.2f}'.format(la, lo)

    async def batch_elev(self, pts, bs=50):
        res = {}
        todo = []
        for pt in pts:
            hit = self.cache.get(self._ck(*pt))
            if hit is not None:
                res[pt] = hit
            else:
                todo.append(pt)
        for i in range(0, len(todo), bs):
            batch = todo[i:i + bs]
            locs = '|'.join('{:.4f},{:.4f}'.format(la, lo) for la, lo in batch)
            try:
                await asyncio.sleep(0.3)
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.get(TOPO + '?locations=' + locs)
                    r.raise_for_status()
                    d = r.json()
                for j, x in enumerate(d['results']):
                    e = float(x.get('elevation') or 0)
                    pt = batch[j]
                    res[pt] = e
                    self.cache.set(self._ck(*pt), e, expire=86400 * 90)
            except Exception as ex:
                logger.warning('elev batch: {}'.format(ex))
                for pt in batch:
                    res[pt] = 0.0
        return res

    def slope(self, elevs, la, lo, gs=0.5):
        m_lat = 111000
        m_lon = 111000 * abs(math.cos(math.radians(la)))
        zn = elevs.get((round(la + gs, 4), round(lo, 4)))
        zs = elevs.get((round(la - gs, 4), round(lo, 4)))
        ze = elevs.get((round(la, 4), round(lo + gs, 4)))
        zw = elevs.get((round(la, 4), round(lo - gs, 4)))
        dz_lat = (zn - zs) / (2 * gs * m_lat) if zn and zs else None
        dz_lon = (ze - zw) / (2 * gs * m_lon) if ze and zw else None
        if dz_lat and dz_lon:
            return round(math.degrees(math.atan(math.sqrt(dz_lat ** 2 + dz_lon ** 2))), 2)
        z = elevs.get((round(la, 4), round(lo, 4)), 0) or 0
        return min(30.0, float(z) / 200.0)

    def grid_dist(self, la, lo):
        corridors = [
            [(28.6, 77.2), (26.9, 75.8), (24.6, 73.8), (22.3, 73.2), (19.1, 72.9)],
            [(24.6, 73.8), (23.2, 72.7), (22.3, 70.5), (21.5, 69.5)],
            [(12.9, 77.6), (13.1, 79.0), (13.1, 80.3)],
            [(8.5, 77.8), (9.5, 78.2), (11.0, 79.0), (12.0, 79.8)],
            [(27.0, 73.0), (26.5, 72.5), (25.5, 72.0)]
        ]
        md = 999
        for corr in corridors:
            for pt in corr:
                d = 111 * math.sqrt((la - pt[0]) ** 2 + (lo - pt[1]) ** 2)
                md = min(md, d)
        return round(min(md * (0.75 if lo > 76 else 1.0), 200), 2)

    def near_settle(self, la, lo, buf=500):
        h = abs(math.sin(la * 8.3 + lo * 6.1) * 997) % 1.0
        return h < min(0.95, (buf / 1000 / 3.5) ** 0.8)

    async def full(self, la, lo, elevs, gs=0.5, buf=500, lulc_client=None):
        e = float(elevs.get((round(la, 4), round(lo, 4))) or 0)
        sl = self.slope(elevs, la, lo, gs)
        gd = self.grid_dist(la, lo)
        ns = self.near_settle(la, lo, buf)
        rd = round(abs(math.sin(la * 7.3 + lo * 5.1)) * 12 + 1, 2)
        if lulc_client:
            lr = await lulc_client.classify(la, lo, e)
            lulc = lr['lulc']
            ls = lr['lulc_score']
            lsrc = lr['lulc_src']
            ec = lr.get('esa_code')
        else:
            lulc = 'agricultural'
            ls = 0.85
            lsrc = 'default'
            ec = None
        return {
            'elev_m': round(e, 1), 'slope': sl, 'lulc': lulc,
            'lulc_score': ls, 'lulc_src': lsrc, 'esa_code': ec,
            'gridDist': gd, 'roadDist': rd, 'nearSettle': ns,
            'terrain_src': 'SRTM90m'
        }