"""
WindSite India v4 - Regulatory Compliance Layer
India-specific exclusion zones for wind energy development.
Sources: MoEFCC, Wildlife Protection Act 1972, Forest Conservation Act 1980,
         PESA Act 1996, DGCA, NHAI guidelines.
"""
import math
import httpx
import asyncio
import diskcache
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger('windsite.regulatory')

_cache = diskcache.Cache('data/cache/terrain')

REGULATORY_BUFFERS = {
    'wildlife_sanctuary':    {'buffer_km': 10.0, 'law': 'Wildlife Protection Act 1972', 'hard': True},
    'national_park':         {'buffer_km': 10.0, 'law': 'Wildlife Protection Act 1972', 'hard': True},
    'tiger_reserve':         {'buffer_km': 10.0, 'law': 'Project Tiger / NTCA',         'hard': True},
    'biosphere_reserve':     {'buffer_km': 5.0,  'law': 'MoEFCC Notification',           'hard': True},
    'ramsar_wetland':        {'buffer_km': 5.0,  'law': 'Ramsar Convention / MoEFCC',    'hard': True},
    'forest_reserved':       {'buffer_km': 1.0,  'law': 'Forest Conservation Act 1980',  'hard': True},
    'forest_protected':      {'buffer_km': 0.5,  'law': 'Forest Conservation Act 1980',  'hard': False},
    'tribal_scheduled':      {'buffer_km': 1.0,  'law': 'PESA Act 1996',                 'hard': False},
    'airport_civil':         {'buffer_km': 20.0, 'law': 'DGCA / AAI Circular',           'hard': True},
    'airport_military':      {'buffer_km': 30.0, 'law': 'MOD / DGCA Circular',           'hard': True},
    'radar_station':         {'buffer_km': 5.0,  'law': 'IMD / DGCA Guidelines',         'hard': True},
    'national_highway':      {'buffer_km': 0.2,  'law': 'NHAI Guidelines',               'hard': False},
    'state_highway':         {'buffer_km': 0.1,  'law': 'PWD Guidelines',                'hard': False},
    'high_voltage_line':     {'buffer_km': 0.05, 'law': 'CEA Technical Standards',       'hard': False},
    'heritage_monument':     {'buffer_km': 0.3,  'law': 'ASI / AMASR Act',               'hard': True},
    'coastal_regulation':    {'buffer_km': 0.5,  'law': 'CRZ Notification 2019',         'hard': True},
}

INDIA_AIRPORTS = [
    {'name': 'Mumbai', 'lat': 19.0896, 'lon': 72.8656, 'type': 'civil'},
    {'name': 'Delhi IGI', 'lat': 28.5562, 'lon': 77.1000, 'type': 'civil'},
    {'name': 'Chennai', 'lat': 12.9941, 'lon': 80.1709, 'type': 'civil'},
    {'name': 'Bengaluru', 'lat': 13.1979, 'lon': 77.7063, 'type': 'civil'},
    {'name': 'Hyderabad', 'lat': 17.2313, 'lon': 78.4298, 'type': 'civil'},
    {'name': 'Ahmedabad', 'lat': 23.0725, 'lon': 72.6347, 'type': 'civil'},
    {'name': 'Jaipur', 'lat': 26.8242, 'lon': 75.8122, 'type': 'civil'},
    {'name': 'Coimbatore', 'lat': 11.0300, 'lon': 77.0434, 'type': 'civil'},
    {'name': 'Madurai', 'lat': 9.8345, 'lon': 78.0934, 'type': 'civil'},
    {'name': 'Tuticorin', 'lat': 8.7242, 'lon': 78.0257, 'type': 'civil'},
    {'name': 'Rajkot', 'lat': 22.3092, 'lon': 70.7794, 'type': 'civil'},
    {'name': 'Bhuj', 'lat': 23.2875, 'lon': 69.6701, 'type': 'civil'},
    {'name': 'Pune', 'lat': 18.5822, 'lon': 73.9197, 'type': 'civil'},
    {'name': 'Nagpur', 'lat': 21.0922, 'lon': 79.0472, 'type': 'civil'},
    {'name': 'Jodhpur', 'lat': 26.2511, 'lon': 73.0489, 'type': 'military'},
    {'name': 'Jaisalmer', 'lat': 26.8887, 'lon': 70.8650, 'type': 'military'},
    {'name': 'Barmer', 'lat': 25.9276, 'lon': 71.3940, 'type': 'military'},
    {'name': 'Bikaner', 'lat': 28.0706, 'lon': 73.2072, 'type': 'military'},
]

PROTECTED_AREAS_INDIA = [
    {'name': 'Gir Forest NP', 'lat': 21.1249, 'lon': 70.7977, 'type': 'national_park', 'radius_km': 40},
    {'name': 'Rann of Kutch Sanctuary', 'lat': 23.7337, 'lon': 70.2000, 'type': 'wildlife_sanctuary', 'radius_km': 80},
    {'name': 'Desert NP Jaisalmer', 'lat': 27.1667, 'lon': 70.8333, 'type': 'national_park', 'radius_km': 60},
    {'name': 'Sariska TR', 'lat': 27.3333, 'lon': 76.3833, 'type': 'tiger_reserve', 'radius_km': 30},
    {'name': 'Ranthambore TR', 'lat': 26.0173, 'lon': 76.5026, 'type': 'tiger_reserve', 'radius_km': 35},
    {'name': 'Keoladeo NP', 'lat': 27.1667, 'lon': 77.5167, 'type': 'national_park', 'radius_km': 15},
    {'name': 'Point Calimere WS', 'lat': 10.2941, 'lon': 79.8516, 'type': 'wildlife_sanctuary', 'radius_km': 20},
    {'name': 'Vedanthangal WS', 'lat': 12.5161, 'lon': 79.8726, 'type': 'wildlife_sanctuary', 'radius_km': 10},
    {'name': 'Chilika Ramsar', 'lat': 19.7167, 'lon': 85.3167, 'type': 'ramsar_wetland', 'radius_km': 30},
    {'name': 'Bhitarkanika NP', 'lat': 20.7500, 'lon': 86.8833, 'type': 'national_park', 'radius_km': 25},
    {'name': 'Nagarhole NP', 'lat': 12.0443, 'lon': 76.1313, 'type': 'national_park', 'radius_km': 30},
    {'name': 'Bandipur TR', 'lat': 11.6667, 'lon': 76.6333, 'type': 'tiger_reserve', 'radius_km': 35},
    {'name': 'Tadoba TR', 'lat': 20.2167, 'lon': 79.3333, 'type': 'tiger_reserve', 'radius_km': 35},
    {'name': 'Melghat TR', 'lat': 21.5000, 'lon': 77.0000, 'type': 'tiger_reserve', 'radius_km': 40},
    {'name': 'Nallamala Forest', 'lat': 15.5000, 'lon': 79.0000, 'type': 'forest_reserved', 'radius_km': 50},
    {'name': 'Eastern Ghats Forest AP', 'lat': 14.5000, 'lon': 79.5000, 'type': 'forest_protected', 'radius_km': 60},
]


def _dist_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def check_regulatory_compliance(lat: float, lon: float) -> Dict:
    """
    Check if a location complies with Indian regulatory requirements.
    Uses hardcoded protected area database + airport proximity.

    Returns:
        dict with compliant (bool), violations (list), warnings (list),
        nearest_protected (dict), nearest_airport (dict)
    """
    violations = []
    warnings = []

    # Check airports
    nearest_airport = None
    min_airport_dist = 999.0
    for ap in INDIA_AIRPORTS:
        d = _dist_km(lat, lon, ap['lat'], ap['lon'])
        if d < min_airport_dist:
            min_airport_dist = d
            nearest_airport = {**ap, 'distance_km': round(d, 2)}
        buf = REGULATORY_BUFFERS['airport_military' if ap['type'] == 'military' else 'airport_civil']
        if d < buf['buffer_km']:
            violations.append({
                'type':    'airport_exclusion',
                'name':    ap['name'],
                'dist_km': round(d, 2),
                'buffer':  buf['buffer_km'],
                'law':     buf['law'],
                'hard':    buf['hard'],
            })

    # Check protected areas
    nearest_pa = None
    min_pa_dist = 999.0
    for pa in PROTECTED_AREAS_INDIA:
        pa_center_dist = _dist_km(lat, lon, pa['lat'], pa['lon'])
        d_to_boundary = max(0.0, pa_center_dist - pa['radius_km'])
        if d_to_boundary < min_pa_dist:
            min_pa_dist = d_to_boundary
            nearest_pa = {**pa, 'dist_to_boundary_km': round(d_to_boundary, 2)}
        buf = REGULATORY_BUFFERS.get(pa['type'], {'buffer_km': 5.0, 'law': 'MoEFCC', 'hard': True})
        if d_to_boundary < buf['buffer_km']:
            item = {
                'type':       pa['type'],
                'name':       pa['name'],
                'dist_km':    round(d_to_boundary, 2),
                'buffer':     buf['buffer_km'],
                'law':        buf['law'],
                'hard':       buf['hard'],
            }
            if buf['hard']:
                violations.append(item)
            else:
                warnings.append(item)

    # CRZ check (coastal areas)
    is_coastal = (lon < 70.0 or lon > 80.5) and (7.5 < lat < 23.0)
    if is_coastal:
        warnings.append({
            'type':    'coastal_regulation',
            'name':    'Potential CRZ area',
            'dist_km': 0,
            'buffer':  0.5,
            'law':     REGULATORY_BUFFERS['coastal_regulation']['law'],
            'hard':    False,
        })

    compliant = len([v for v in violations if v['hard']]) == 0

    return {
        'compliant':         compliant,
        'violations':        violations,
        'warnings':          warnings,
        'n_violations':      len(violations),
        'n_warnings':        len(warnings),
        'nearest_airport':   nearest_airport,
        'nearest_protected': nearest_pa,
        'source':            'MoEFCC + DGCA + hardcoded India database',
    }


async def check_osm_protected_areas(lat: float, lon: float, radius_km: float = 15.0) -> Dict:
    """
    Query OSM for protected areas near a point.
    Supplements the hardcoded database with real OSM data.
    """
    cache_key = 'reg_osm_{:.2f}_{:.2f}'.format(lat, lon)
    hit = _cache.get(cache_key)
    if hit is not None:
        return hit

    query = (
        '[out:json][timeout:20];'
        '('
        '  way["boundary"="protected_area"](around:{r},{lat},{lon});'
        '  relation["boundary"="protected_area"](around:{r},{lat},{lon});'
        '  way["leisure"="nature_reserve"](around:{r},{lat},{lon});'
        '  relation["leisure"="nature_reserve"](around:{r},{lat},{lon});'
        ');'
        'out tags 10;'
    ).format(r=int(radius_km * 1000), lat=round(lat, 4), lon=round(lon, 4))

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                'https://overpass-api.de/api/interpreter',
                data={'data': query},
                headers={'Accept': 'application/json'}
            )
        if resp.status_code != 200:
            return {'osm_protected': [], 'source': 'osm-failed'}
        data = resp.json()
        areas = []
        for el in data.get('elements', []):
            tags = el.get('tags', {})
            name = tags.get('name', tags.get('ref', 'Unnamed'))
            ptype = tags.get('boundary', tags.get('leisure', 'protected'))
            iucn = tags.get('iucn_level', '')
            areas.append({
                'name':  name,
                'type':  ptype,
                'iucn':  iucn,
                'osm_id': el.get('id'),
            })
        result = {'osm_protected': areas, 'n_areas': len(areas), 'source': 'OpenStreetMap'}
        _cache.set(cache_key, result, expire=86400 * 30)
        return result
    except Exception as e:
        logger.warning('OSM protected areas failed: {}'.format(e))
        return {'osm_protected': [], 'source': 'osm-failed', 'error': str(e)}


def regulatory_score(compliance_result: Dict) -> float:
    """
    Convert compliance result to a 0-1 suitability score.
    Hard violations = 0, warnings reduce score.
    """
    if not compliance_result.get('compliant', True):
        return 0.0
    n_warnings = compliance_result.get('n_warnings', 0)
    score = max(0.1, 1.0 - n_warnings * 0.15)
    nearest_ap = compliance_result.get('nearest_airport', {})
    if nearest_ap:
        d = nearest_ap.get('distance_km', 100)
        if d < 30:
            score *= (d / 30.0)
    return round(score, 3)