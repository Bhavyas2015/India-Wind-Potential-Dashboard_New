import asyncio
import httpx
import diskcache
import logging
import math

logger = logging.getLogger('windsite.lulc')
STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1/collections/esa-worldcover/items'
SIGN = 'https://planetarycomputer.microsoft.com/api/sas/v1/sign'

E2W = {10: 'forest', 20: 'shrubland', 30: 'open', 40: 'agricultural',
       50: 'urban', 60: 'open', 70: 'open', 80: 'water',
       90: 'wetland', 95: 'water', 100: 'open'}
ELA = {10: 'Tree cover', 20: 'Shrubland', 30: 'Grassland', 40: 'Cropland',
       50: 'Built-up', 60: 'Bare veg', 80: 'Water', 90: 'Wetland'}
SCR = {'open': 1.0, 'agricultural': 0.85, 'shrubland': 0.75, 'forest': 0.2,
       'urban': 0.0, 'water': 0.0, 'wetland': 0.1, 'protected': 0.0, 'unknown': 0.5}

_tc = {}
_sc = {}


def _tkey(la, lo):
    lb = int(math.floor(la / 3)) * 3
    lo2 = int(math.floor(lo / 3)) * 3
    return ('N' if lb >= 0 else 'S') + '{:02d}'.format(abs(lb)) + ('E' if lo2 >= 0 else 'W') + '{:03d}'.format(abs(lo2))


async def _get_signed(la, lo):
    tk = _tkey(la, lo)
    if tk in _sc:
        return _sc[tk]
    try:
        if tk not in _tc:
            p = {'bbox': '{},{},{},{}'.format(lo - 0.01, la - 0.01, lo + 0.01, la + 0.01), 'limit': '1'}
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(STAC, params=p)
            ft = r.json().get('features', [])
            if not ft:
                return None
            _tc[tk] = ft[0]['assets']['map']['href']
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(SIGN, params={'href': _tc[tk]})
        if r.status_code != 200:
            return None
        _sc[tk] = r.json().get('href')
        return _sc[tk]
    except Exception as ex:
        logger.warning('sign: {}'.format(ex))
        return None


def _px(url, la, lo):
    try:
        import rasterio
        from rasterio.transform import rowcol
        from rasterio.windows import Window
        with rasterio.open(url) as ds:
            row, col = rowcol(ds.transform, lo, la)
            row = int(max(0, min(int(row), ds.height - 1)))
            col = int(max(0, min(int(col), ds.width - 1)))
            return int(ds.read(1, window=Window(col, row, 1, 1))[0][0])
    except Exception as ex:
        logger.warning('px: {}'.format(ex))
        return None


def _heur(la, lo, elev=0):
    uc = [(23.03, 72.58, 50), (26.91, 75.79, 40), (13.08, 80.27, 45),
          (19.07, 72.88, 60), (17.39, 78.49, 50), (12.97, 77.59, 50), (28.61, 77.21, 60)]
    for a, b, r in uc:
        if 111 * math.sqrt((la - a) ** 2 + (lo - b) ** 2) < r:
            return 'urban'
    if lo < 68.5 or lo > 88.5 or la < 7.5 or la > 37.5:
        return 'water'
    if elev > 700:
        return 'forest'
    if 300 < elev <= 700 and lo < 77:
        return 'forest'
    if 22.5 < la < 24.5 and 69 < lo < 71.5:
        return 'protected'
    if la > 25 and lo < 73:
        return 'open'
    return 'agricultural'


def _res(cat, code, src):
    return {'lulc': cat, 'lulc_score': SCR.get(cat, 0.5),
            'esa_code': code, 'esa_label': ELA.get(code, ''), 'lulc_src': src}


class LULCClient:
    def __init__(self, cache_dir='data/cache/lulc'):
        self.cache = diskcache.Cache(cache_dir)

    def _ck(self, la, lo):
        return 'lulc_{:.3f}_{:.3f}'.format(la, lo)

    async def classify(self, la, lo, elev_m=0):
        k = self._ck(la, lo)
        hit = self.cache.get(k)
        if hit:
            return hit
        url = await _get_signed(la, lo)
        if url:
            code = await asyncio.get_event_loop().run_in_executor(None, _px, url, la, lo)
            if code and code in E2W:
                res = _res(E2W[code], code, 'ESA_WorldCover_10m')
                self.cache.set(k, res, expire=86400 * 180)
                return res
        res = _res(_heur(la, lo, elev_m), None, 'heuristic')
        self.cache.set(k, res, expire=86400 * 7)
        return res