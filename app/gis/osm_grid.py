"""
WindSite India v4 - Real Grid Infrastructure Distance
Uses OpenStreetMap Overpass API to find actual power line locations.
Replaces hardcoded corridor approximations with real 220kV/400kV/765kV lines.
"""
import httpx
import asyncio
import diskcache
import math
import logging
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger('windsite.osm_grid')

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'

VOLTAGE_LEVELS = {
    '765000': {'label': '765kV', 'color': '#ff3d57', 'priority': 1},
    '400000': {'label': '400kV', 'color': '#ff7a00', 'priority': 2},
    '220000': {'label': '220kV', 'color': '#ffb800', 'priority': 3},
    '132000': {'label': '132kV', 'color': '#00d084', 'priority': 4},
    '110000': {'label': '110kV', 'color': '#1a8cff', 'priority': 5},
    '66000':  {'label': '66kV',  'color': '#9b6dff', 'priority': 6},
    '33000':  {'label': '33kV',  'color': '#4a6278', 'priority': 7},
}

_cache = diskcache.Cache('data/cache/terrain')


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


async def fetch_power_lines_near(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
    voltage_min: int = 66000
) -> List[Dict]:
    """
    Fetch power transmission lines from OSM Overpass API.

    Parameters:
        lat, lon:     center point
        radius_km:    search radius in km
        voltage_min:  minimum voltage to include (default 66kV)

    Returns:
        list of power line segments with voltage and distance info
    """
    cache_key = 'osm_grid_{:.2f}_{:.2f}_{:.0f}'.format(lat, lon, radius_km)
    hit = _cache.get(cache_key)
    if hit is not None:
        return hit

    radius_m = int(radius_km * 1000)

    query = (
        '[out:json][timeout:25];'
        '('
        '  way["power"="line"]["voltage"~"^(33|66|110|132|220|400|765)[0-9]*000$"]'
        '  (around:{r},{lat},{lon});'
        '  way["power"="cable"]["voltage"~"^(33|66|110|132|220|400|765)[0-9]*000$"]'
        '  (around:{r},{lat},{lon});'
        ');'
        'out geom;'
    ).format(r=radius_m, lat=round(lat, 4), lon=round(lon, 4))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OVERPASS_URL,
                data={'data': query},
                headers={'Accept': 'application/json'}
            )
            if resp.status_code != 200:
                logger.warning('Overpass HTTP {}'.format(resp.status_code))
                return []
            data = resp.json()

        lines = []
        for el in data.get('elements', []):
            if el.get('type') != 'way':
                continue
            tags = el.get('tags', {})
            voltage_str = tags.get('voltage', '0').split(';')[0].strip()
            try:
                voltage = int(voltage_str)
            except Exception:
                continue

            if voltage < voltage_min:
                continue

            geometry = el.get('geometry', [])
            if not geometry:
                continue

            min_dist = min(
                _haversine(lat, lon, node['lat'], node['lon'])
                for node in geometry
            )

            vkey = str(voltage)
            label = VOLTAGE_LEVELS.get(vkey, {}).get('label', str(voltage // 1000) + 'kV')

            lines.append({
                'osm_id':       el.get('id'),
                'voltage':      voltage,
                'voltage_kv':   voltage // 1000,
                'label':        label,
                'distance_km':  round(min_dist, 2),
                'name':         tags.get('name', ''),
                'operator':     tags.get('operator', ''),
                'nodes':        len(geometry),
            })

        lines.sort(key=lambda x: x['distance_km'])
        _cache.set(cache_key, lines, expire=86400 * 7)
        return lines

    except Exception as e:
        logger.warning('OSM grid fetch failed: {}'.format(e))
        return []


async def nearest_grid_distance(
    lat: float,
    lon: float,
    voltage_min: int = 66000,
    radius_km: float = 80.0
) -> Dict:
    """
    Get distance to nearest grid line of sufficient voltage.

    Returns:
        dict with distance_km, voltage_kv, label, source
    """
    lines = await fetch_power_lines_near(lat, lon, radius_km, voltage_min)

    if lines:
        nearest = lines[0]
        return {
            'gridDist':      nearest['distance_km'],
            'gridVoltage':   nearest['voltage_kv'],
            'gridLabel':     nearest['label'],
            'gridOperator':  nearest['operator'],
            'gridSource':    'OpenStreetMap',
            'gridOsmId':     nearest['osm_id'],
        }

    # Fallback to hardcoded corridors
    fallback_dist = _fallback_grid_dist(lat, lon)
    return {
        'gridDist':     fallback_dist,
        'gridVoltage':  220,
        'gridLabel':    '220kV (estimated)',
        'gridOperator': '',
        'gridSource':   'heuristic',
        'gridOsmId':    None,
    }


def _fallback_grid_dist(lat: float, lon: float) -> float:
    corridors = [
        [(28.6, 77.2), (26.9, 75.8), (24.6, 73.8), (22.3, 73.2), (19.1, 72.9)],
        [(24.6, 73.8), (23.2, 72.7), (22.3, 70.5), (21.5, 69.5)],
        [(12.9, 77.6), (13.1, 79.0), (13.1, 80.3)],
        [(8.5, 77.8), (9.5, 78.2), (11.0, 79.0), (12.0, 79.8)],
        [(27.0, 73.0), (26.5, 72.5), (25.5, 72.0)],
    ]
    min_d = 999.0
    for corr in corridors:
        for pt in corr:
            d = _haversine(lat, lon, pt[0], pt[1])
            min_d = min(min_d, d)
    return round(min(min_d * (0.75 if lon > 76 else 1.0), 200.0), 2)


async def batch_grid_distances(
    points: List[Tuple[float, float]],
    voltage_min: int = 66000,
    max_concurrent: int = 3
) -> Dict[Tuple[float, float], Dict]:
    """
    Fetch grid distances for multiple points with rate limiting.
    """
    sem = asyncio.Semaphore(max_concurrent)
    results = {}

    async def one(lat, lon):
        async with sem:
            await asyncio.sleep(1.0)
            results[(lat, lon)] = await nearest_grid_distance(lat, lon, voltage_min)

    await asyncio.gather(*[one(la, lo) for la, lo in points])
    return results