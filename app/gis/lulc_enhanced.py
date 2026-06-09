"""
WindSite India v4 - Enhanced LULC Coverage
Full ESA WorldCover 10m raster coverage across all Indian states.
Replaces heuristic fallback with actual COG tile reading.
Also adds NDVI-based vegetation classification as backup.
"""
import asyncio
import httpx
import diskcache
import logging
import math
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger('windsite.lulc_enhanced')

_cache = diskcache.Cache('data/cache/lulc')

# ESA WorldCover 10m - Full India tile index
# Tiles cover 3x3 degree blocks
INDIA_TILES = [
    # Gujarat
    ('N18E066','N18E069','N18E072'),
    ('N21E066','N21E069','N21E072'),
    ('N24E069','N24E072','N24E075'),
    # Rajasthan
    ('N24E069','N24E072','N24E075','N24E078'),
    ('N27E069','N27E072','N27E075','N27E078'),
    ('N30E069','N30E072','N30E075','N30E078'),
    # Tamil Nadu
    ('N06E078','N06E081'),
    ('N09E078','N09E081'),
    ('N12E078','N12E081'),
    # Maharashtra
    ('N15E072','N15E075','N15E078'),
    ('N18E072','N18E075','N18E078'),
    ('N21E072','N21E075','N21E078'),
    # Andhra
    ('N12E078','N12E081','N12E084'),
    ('N15E078','N15E081','N15E084'),
    ('N18E078','N18E081','N18E084'),
    # Karnataka
    ('N12E075','N12E078'),
    ('N15E075','N15E078'),
]

# ESA WorldCover class definitions
ESA_CLASSES = {
    10:  {'name': 'Tree cover',         'lulc': 'forest',       'score': 0.10, 'color': '#1b5e20'},
    20:  {'name': 'Shrubland',          'lulc': 'shrubland',    'score': 0.75, 'color': '#8bc34a'},
    30:  {'name': 'Grassland',          'lulc': 'open',         'score': 1.00, 'color': '#cddc39'},
    40:  {'name': 'Cropland',           'lulc': 'agricultural', 'score': 0.85, 'color': '#ffeb3b'},
    50:  {'name': 'Built-up',           'lulc': 'urban',        'score': 0.00, 'color': '#f44336'},
    60:  {'name': 'Bare/sparse veg',    'lulc': 'open',         'score': 1.00, 'color': '#ff9800'},
    70:  {'name': 'Snow and ice',       'lulc': 'open',         'score': 0.50, 'color': '#e0e0e0'},
    80:  {'name': 'Permanent water',    'lulc': 'water',        'score': 0.00, 'color': '#2196f3'},
    90:  {'name': 'Herbaceous wetland', 'lulc': 'wetland',      'score': 0.10, 'color': '#607d8b'},
    95:  {'name': 'Mangroves',          'lulc': 'water',        'score': 0.00, 'color': '#004d40'},
    100: {'name': 'Moss and lichen',    'lulc': 'open',         'score': 0.80, 'color': '#a5d6a7'},
}

STAC_BASE = 'https://planetarycomputer.microsoft.com/api/stac/v1'
SIGN_BASE = 'https://planetarycomputer.microsoft.com/api/sas/v1/sign'

_signed_urls = {}
_stac_items  = {}


def _tile_key(lat: float, lon: float) -> str:
    lb = int(math.floor(lat / 3)) * 3
    lo = int(math.floor(lon / 3)) * 3
    ns = 'N' if lb >= 0 else 'S'
    ew = 'E' if lo >= 0 else 'W'
    return '{}{:02d}{}{:03d}'.format(ns, abs(lb), ew, abs(lo))


async def _get_tile_url(tile_key: str) -> Optional[str]:
    if tile_key in _signed_urls:
        return _signed_urls[tile_key]
    try:
        # Search STAC for tile
        lat_approx = int(tile_key[1:3]) * (1 if tile_key[0] == 'N' else -1)
        lon_approx = int(tile_key[4:7]) * (1 if tile_key[3] == 'E' else -1)
        bbox = '{},{},{},{}'.format(
            lon_approx, lat_approx,
            lon_approx + 3, lat_approx + 3
        )
        params = {
            'collections': 'esa-worldcover',
            'bbox': bbox,
            'limit': '1'
        }
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.get(STAC_BASE + '/search', params=params)
            if r.status_code != 200:
                return None
            features = r.json().get('features', [])
            if not features:
                return None
            href = features[0]['assets']['map']['href']
            _stac_items[tile_key] = href

        # Sign the URL
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.get(SIGN_BASE, params={'href': href})
            if r.status_code != 200:
                return None
            signed = r.json().get('href')
            _signed_urls[tile_key] = signed
            return signed
    except Exception as e:
        logger.warning('Tile {} URL failed: {}'.format(tile_key, e))
        return None


def _read_pixel(url: str, lat: float, lon: float) -> Optional[int]:
    try:
        import rasterio
        from rasterio.transform import rowcol
        from rasterio.windows import Window
        with rasterio.open(url) as ds:
            row, col = rowcol(ds.transform, lon, lat)
            row = int(max(0, min(int(row), ds.height - 1)))
            col = int(max(0, min(int(col), ds.width  - 1)))
            val = int(ds.read(1, window=Window(col, row, 1, 1))[0][0])
            return val
    except Exception as e:
        logger.warning('Pixel read failed: {}'.format(e))
        return None


def _india_heuristic(lat: float, lon: float, elev: float = 0) -> Dict:
    """
    Improved heuristic using geographic context.
    Much more accurate than simple random assignment.
    """
    # Urban centres with radius
    urban_centres = [
        (23.03, 72.58, 45),  # Ahmedabad
        (22.30, 73.20, 25),  # Vadodara
        (21.20, 72.84, 20),  # Surat
        (26.91, 75.79, 35),  # Jaipur
        (26.28, 73.02, 20),  # Jodhpur
        (28.02, 73.31, 15),  # Bikaner
        (13.08, 80.27, 40),  # Chennai
        (11.00, 76.96, 25),  # Coimbatore
        (9.93,  78.12, 20),  # Madurai
        (19.07, 72.88, 60),  # Mumbai
        (18.52, 73.86, 35),  # Pune
        (21.15, 79.08, 20),  # Nagpur
        (17.38, 78.49, 45),  # Hyderabad
        (14.68, 77.59, 15),  # Kurnool
        (12.97, 77.59, 50),  # Bengaluru
        (15.33, 75.13, 20),  # Dharwad
        (28.61, 77.21, 60),  # Delhi
    ]
    for clat, clon, r in urban_centres:
        if 111 * math.sqrt((lat - clat)**2 + (lon - clon)**2) < r:
            return {'lulc': 'urban', 'score': 0.0, 'code': 50, 'src': 'heuristic-urban'}

    # Water bodies
    if lon < 68.0 or lon > 89.0 or lat < 7.0 or lat > 36.0:
        return {'lulc': 'water', 'score': 0.0, 'code': 80, 'src': 'heuristic-water'}

    # Coastal water/mangroves
    if lat < 9.0 and lon > 78.0:
        return {'lulc': 'water', 'score': 0.0, 'code': 95, 'src': 'heuristic-mangrove'}

    # High elevation forest (Western/Eastern Ghats, Himalayan foothills)
    if elev > 900:
        return {'lulc': 'forest', 'score': 0.10, 'code': 10, 'src': 'heuristic-elev-forest'}
    if elev > 600 and (lon < 77.5 or (lat < 14 and lon > 77)):
        return {'lulc': 'forest', 'score': 0.15, 'code': 10, 'src': 'heuristic-ghats-forest'}

    # Protected/sanctuary areas
    protected_zones = [
        (21.12, 70.80, 35),  # Gir
        (23.73, 70.20, 70),  # Rann of Kutch
        (27.17, 70.83, 55),  # Desert NP
        (26.02, 76.50, 30),  # Ranthambore
        (11.67, 76.63, 30),  # Bandipur
        (12.04, 76.13, 25),  # Nagarhole
    ]
    for plat, plon, r in protected_zones:
        if 111 * math.sqrt((lat - plat)**2 + (lon - plon)**2) < r:
            return {'lulc': 'protected', 'score': 0.0, 'code': 10, 'src': 'heuristic-protected'}

    # Thar Desert (Rajasthan) - excellent for wind
    if lat > 25 and lon < 73.5:
        return {'lulc': 'open', 'score': 1.0, 'code': 60, 'src': 'heuristic-desert'}

    # Gujarat plains
    if 20 < lat < 24 and 68 < lon < 74:
        return {'lulc': 'open', 'score': 0.95, 'code': 30, 'src': 'heuristic-gujarat-plain'}

    # Deccan plateau cropland
    if 15 < lat < 22 and 73 < lon < 80:
        return {'lulc': 'agricultural', 'score': 0.85, 'code': 40, 'src': 'heuristic-deccan'}

    # Tamil Nadu coast
    if lat < 13 and lon > 78:
        return {'lulc': 'agricultural', 'score': 0.80, 'code': 40, 'src': 'heuristic-tn-coast'}

    return {'lulc': 'agricultural', 'score': 0.80, 'code': 40, 'src': 'heuristic-default'}


async def classify_enhanced(
    lat: float,
    lon: float,
    elev_m: float = 0.0,
    use_raster: bool = True
) -> Dict:
    """
    Enhanced LULC classification with full ESA WorldCover 10m coverage.
    Falls back to improved heuristic if raster unavailable.
    """
    cache_key = 'lulc_enh_{:.3f}_{:.3f}'.format(lat, lon)
    hit = _cache.get(cache_key)
    if hit:
        return hit

    if use_raster:
        tile_key = _tile_key(lat, lon)
        url = await _get_tile_url(tile_key)
        if url:
            loop = asyncio.get_event_loop()
            code = await loop.run_in_executor(None, _read_pixel, url, lat, lon)
            if code and code in ESA_CLASSES:
                cls = ESA_CLASSES[code]
                result = {
                    'lulc':       cls['lulc'],
                    'lulc_score': cls['score'],
                    'esa_code':   code,
                    'esa_label':  cls['name'],
                    'esa_color':  cls['color'],
                    'lulc_src':   'ESA_WorldCover_10m',
                    'tile':       tile_key,
                }
                _cache.set(cache_key, result, expire=86400 * 180)
                return result

    # Improved heuristic fallback
    h = _india_heuristic(lat, lon, elev_m)
    code = h['code']
    cls = ESA_CLASSES.get(code, ESA_CLASSES[40])
    result = {
        'lulc':       h['lulc'],
        'lulc_score': h['score'],
        'esa_code':   code,
        'esa_label':  cls['name'],
        'esa_color':  cls['color'],
        'lulc_src':   h['src'],
        'tile':       _tile_key(lat, lon),
    }
    _cache.set(cache_key, result, expire=86400 * 7)
    return result


async def classify_batch_enhanced(
    points: List[Tuple[float, float]],
    elevs: Dict = None,
    max_concurrent: int = 6
) -> Dict[Tuple[float, float], Dict]:
    """
    Classify LULC for multiple points efficiently.
    Pre-signs all required tiles before processing.
    """
    elevs = elevs or {}

    # Pre-sign all unique tiles
    tile_keys = set(_tile_key(la, lo) for la, lo in points)
    logger.info('Pre-signing {} ESA WorldCover tiles...'.format(len(tile_keys)))

    for tk in tile_keys:
        await _get_tile_url(tk)

    sem = asyncio.Semaphore(max_concurrent)
    results = {}

    async def one(lat, lon):
        async with sem:
            elev = elevs.get((lat, lon), 0.0)
            results[(lat, lon)] = await classify_enhanced(lat, lon, elev)

    await asyncio.gather(*[one(la, lo) for la, lo in points])
    return results


def lulc_stats(results: Dict) -> Dict:
    """Summarise LULC classification results."""
    counts = {}
    scores = []
    for r in results.values():
        lulc = r.get('lulc', 'unknown')
        counts[lulc] = counts.get(lulc, 0) + 1
        scores.append(r.get('lulc_score', 0.5))
    total = len(results)
    return {
        'total':          total,
        'distribution':   {k: round(v / total * 100, 1) for k, v in counts.items()},
        'mean_score':     round(sum(scores) / max(len(scores), 1), 3),
        'suitable_pct':   round(sum(1 for s in scores if s > 0.5) / max(total, 1) * 100, 1),
        'excluded_pct':   round(sum(1 for s in scores if s == 0) / max(total, 1) * 100, 1),
    }