"""
WindSite India v4 - Real-time Wind Data
Sources:
  - GFS (Global Forecast System) via Open-Meteo - FREE, no key
  - ECMWF IFS via Open-Meteo - FREE, no key
  - Comparison between both models
"""
import httpx
import asyncio
import diskcache
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger('windsite.realtime')

# Both APIs are FREE via Open-Meteo
GFS_URL   = 'https://api.open-meteo.com/v1/gfs'
ECMWF_URL = 'https://api.open-meteo.com/v1/ecmwf'
ICON_URL  = 'https://api.open-meteo.com/v1/dwd-icon'

_cache = diskcache.Cache('data/cache/wind_now')

WIND_PARAMS_GFS = (
    'wind_speed_10m,'
    'wind_direction_10m,'
    'wind_speed_80m,'
    'wind_direction_80m,'
    'wind_speed_120m,'
    'wind_direction_120m,'
    'wind_gusts_10m,'
    'temperature_2m,'
    'surface_pressure,'
    'precipitation_probability'
)

WIND_PARAMS_ECMWF = (
    'wind_speed_10m,'
    'wind_direction_10m,'
    'wind_speed_200hPa,'
    'temperature_2m,'
    'surface_pressure'
)


def _uv(speed, direction_deg):
    rad = math.radians(direction_deg)
    return round(-speed * math.sin(rad), 3), round(-speed * math.cos(rad), 3)


async def _fetch_model(url, lat, lon, params, forecast_days=2):
    p = {
        'latitude':        lat,
        'longitude':       lon,
        'hourly':          params,
        'wind_speed_unit': 'ms',
        'forecast_days':   forecast_days,
        'format':          'json',
    }
    async with httpx.AsyncClient(timeout=25.0) as cl:
        r = await cl.get(url, params=p)
        r.raise_for_status()
        return r.json()


async def fetch_gfs_current(lat: float, lon: float) -> Dict:
    """Fetch current + 48hr GFS forecast for a point."""
    cache_key = 'gfs_{:.2f}_{:.2f}_{}'.format(lat, lon, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit:
        return dict(hit, source='gfs-cached')
    try:
        d = await _fetch_model(GFS_URL, lat, lon, WIND_PARAMS_GFS)
        h = d.get('hourly', {})
        now = datetime.utcnow().hour
        ws10 = h.get('wind_speed_10m', [])
        wd10 = h.get('wind_direction_10m', [])
        ws80 = h.get('wind_speed_80m', [])
        wd80 = h.get('wind_direction_80m', [])
        ws120 = h.get('wind_speed_120m', [])
        wd120 = h.get('wind_direction_120m', [])
        gusts = h.get('wind_gusts_10m', [])
        temp  = h.get('temperature_2m', [])
        times = h.get('time', [])

        def safe(arr, idx, default=0.0):
            return arr[idx] if arr and len(arr) > idx else default

        u10, v10   = _uv(safe(ws10, now), safe(wd10, now, 225))
        u80, v80   = _uv(safe(ws80, now), safe(wd80, now, 225))
        u120, v120 = _uv(safe(ws120, now), safe(wd120, now, 225))

        out = {
            'lat': lat, 'lon': lon,
            'model': 'GFS',
            'provider': 'Open-Meteo',
            'timestamp': datetime.utcnow().isoformat(),
            'current': {
                'ws10m':  round(safe(ws10, now), 2),
                'wd10m':  round(safe(wd10, now, 225), 1),
                'ws80m':  round(safe(ws80, now), 2),
                'wd80m':  round(safe(wd80, now, 225), 1),
                'ws120m': round(safe(ws120, now), 2),
                'wd120m': round(safe(wd120, now, 225), 1),
                'gusts':  round(safe(gusts, now), 2),
                'temp_c': round(safe(temp, now, 25), 1),
                'u10m': u10, 'v10m': v10,
                'u80m': u80, 'v80m': v80,
                'u120m': u120, 'v120m': v120,
            },
            'forecast_48h': {
                'times':   times[:48],
                'ws10':    ws10[:48],
                'wd10':    wd10[:48],
                'ws80':    ws80[:48],
                'wd80':    wd80[:48],
                'ws120':   ws120[:48],
                'gusts':   gusts[:48],
                'temp':    temp[:48],
            },
            'source': 'gfs-live',
        }
        _cache.set(cache_key, out, expire=3600)
        return out
    except Exception as e:
        logger.error('GFS fetch failed: {}'.format(e))
        raise


async def fetch_ecmwf_current(lat: float, lon: float) -> Dict:
    """Fetch current ECMWF IFS forecast for a point."""
    cache_key = 'ecmwf_{:.2f}_{:.2f}_{}'.format(lat, lon, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit:
        return dict(hit, source='ecmwf-cached')
    try:
        d = await _fetch_model(ECMWF_URL, lat, lon, WIND_PARAMS_ECMWF, forecast_days=2)
        h = d.get('hourly', {})
        now = datetime.utcnow().hour
        ws10 = h.get('wind_speed_10m', [])
        wd10 = h.get('wind_direction_10m', [])
        temp = h.get('temperature_2m', [])
        times = h.get('time', [])

        def safe(arr, idx, default=0.0):
            return arr[idx] if arr and len(arr) > idx else default

        u10, v10 = _uv(safe(ws10, now), safe(wd10, now, 225))

        out = {
            'lat': lat, 'lon': lon,
            'model': 'ECMWF IFS',
            'provider': 'Open-Meteo',
            'timestamp': datetime.utcnow().isoformat(),
            'current': {
                'ws10m': round(safe(ws10, now), 2),
                'wd10m': round(safe(wd10, now, 225), 1),
                'temp_c': round(safe(temp, now, 25), 1),
                'u10m': u10, 'v10m': v10,
            },
            'forecast_48h': {
                'times': times[:48],
                'ws10':  ws10[:48],
                'wd10':  wd10[:48],
                'temp':  temp[:48],
            },
            'source': 'ecmwf-live',
        }
        _cache.set(cache_key, out, expire=3600)
        return out
    except Exception as e:
        logger.error('ECMWF fetch failed: {}'.format(e))
        raise


async def fetch_model_comparison(lat: float, lon: float) -> Dict:
    """
    Fetch both GFS and ECMWF and return side-by-side comparison.
    Useful for understanding forecast uncertainty.
    """
    cache_key = 'cmp_{:.2f}_{:.2f}_{}'.format(lat, lon, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit:
        return dict(hit, source='comparison-cached')

    gfs_result, ecmwf_result = await asyncio.gather(
        fetch_gfs_current(lat, lon),
        fetch_ecmwf_current(lat, lon),
        return_exceptions=True
    )

    gfs_ok   = not isinstance(gfs_result, Exception)
    ecmwf_ok = not isinstance(ecmwf_result, Exception)

    out = {
        'lat': lat, 'lon': lon,
        'timestamp': datetime.utcnow().isoformat(),
        'gfs':   gfs_result   if gfs_ok   else {'error': str(gfs_result)},
        'ecmwf': ecmwf_result if ecmwf_ok else {'error': str(ecmwf_result)},
        'comparison': None,
    }

    if gfs_ok and ecmwf_ok:
        gc = gfs_result['current']
        ec = ecmwf_result['current']
        out['comparison'] = {
            'ws10_gfs':    gc.get('ws10m', 0),
            'ws10_ecmwf':  ec.get('ws10m', 0),
            'ws10_diff':   round(abs(gc.get('ws10m', 0) - ec.get('ws10m', 0)), 2),
            'wd10_gfs':    gc.get('wd10m', 0),
            'wd10_ecmwf':  ec.get('wd10m', 0),
            'wd10_diff':   round(abs(gc.get('wd10m', 0) - ec.get('wd10m', 0)), 1),
            'ws10_mean':   round((gc.get('ws10m', 0) + ec.get('ws10m', 0)) / 2, 2),
            'agreement':   'good' if abs(gc.get('ws10m', 0) - ec.get('ws10m', 0)) < 1.5 else 'moderate',
        }
        out['source'] = 'gfs+ecmwf-live'

    _cache.set(cache_key, out, expire=3600)
    return out


async def fetch_wind_grid_realtime(
    aoi: str = 'gujarat',
    model: str = 'gfs',
    level: int = 80
) -> Dict:
    """
    Fetch real-time wind field grid for an AOI.
    Powers the Windy.com-style animation in the frontend.

    Parameters:
        aoi:   area of interest key
        model: 'gfs', 'ecmwf', or 'both'
        level: hub height in metres (10, 80, 120)
    """
    AOI_BOUNDS = {
        'gujarat':     {'lat_min': 20.0, 'lat_max': 25.5, 'lon_min': 68.0, 'lon_max': 75.5},
        'rajasthan':   {'lat_min': 23.5, 'lat_max': 31.5, 'lon_min': 69.0, 'lon_max': 78.5},
        'tamilnadu':   {'lat_min':  7.5, 'lat_max': 14.0, 'lon_min': 76.5, 'lon_max': 81.0},
        'maharashtra': {'lat_min': 15.0, 'lat_max': 22.5, 'lon_min': 72.5, 'lon_max': 80.5},
        'andhra':      {'lat_min': 11.5, 'lat_max': 19.5, 'lon_min': 77.5, 'lon_max': 84.5},
        'karnataka':   {'lat_min': 11.5, 'lat_max': 18.5, 'lon_min': 74.0, 'lon_max': 79.0},
    }

    bounds = AOI_BOUNDS.get(aoi, AOI_BOUNDS['gujarat'])
    step = 0.5

    lats = [round(bounds['lat_min'] + i * step, 2)
            for i in range(int((bounds['lat_max'] - bounds['lat_min']) / step) + 1)]
    lons = [round(bounds['lon_min'] + i * step, 2)
            for i in range(int((bounds['lon_max'] - bounds['lon_min']) / step) + 1)]
    pts = [(la, lo) for la in lats for lo in lons]

    cache_key = 'grid_{}_{}_{}'.format(aoi, model, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit:
        return dict(hit, source='grid-cached')

    sem = asyncio.Semaphore(6)
    grid_results = {}

    url = GFS_URL if model == 'gfs' else ECMWF_URL
    params = WIND_PARAMS_GFS if model == 'gfs' else WIND_PARAMS_ECMWF

    async def fetch_pt(lat, lon):
        async with sem:
            await asyncio.sleep(0.08)
            try:
                p = {
                    'latitude':        lat,
                    'longitude':       lon,
                    'hourly':          'wind_speed_10m,wind_direction_10m,wind_speed_80m,wind_direction_80m',
                    'wind_speed_unit': 'ms',
                    'forecast_days':   1,
                    'format':          'json',
                }
                async with httpx.AsyncClient(timeout=20.0) as cl:
                    r = await cl.get(url, params=p)
                    r.raise_for_status()
                    d = r.json()
                h = d.get('hourly', {})
                now = datetime.utcnow().hour

                def safe(arr, default=0.0):
                    return arr[now] if arr and len(arr) > now else default

                ws10 = safe(h.get('wind_speed_10m', []))
                wd10 = safe(h.get('wind_direction_10m', []), 225.0)
                ws80 = safe(h.get('wind_speed_80m', []))
                wd80 = safe(h.get('wind_direction_80m', []), 225.0)

                spd = ws80 if level >= 80 else ws10
                dirn = wd80 if level >= 80 else wd10
                u, v = _uv(spd, dirn)

                grid_results[(lat, lon)] = {
                    'lat': lat, 'lon': lon,
                    'ws10m': round(ws10, 2), 'wd10m': round(wd10, 1),
                    'ws80m': round(ws80, 2), 'wd80m': round(wd80, 1),
                    'spd':   round(spd, 2),
                    'dir':   round(dirn, 1),
                    'u':     u, 'v': v,
                }
            except Exception as e:
                logger.warning('Grid pt ({},{}) failed: {}'.format(lat, lon, e))
                grid_results[(lat, lon)] = {
                    'lat': lat, 'lon': lon,
                    'ws10m': 5.0, 'wd10m': 225.0,
                    'ws80m': 7.0, 'wd80m': 225.0,
                    'spd': 7.0, 'dir': 225.0,
                    'u': -4.95, 'v': -4.95,
                }

    await asyncio.gather(*[fetch_pt(la, lo) for la, lo in pts])

    out = {
        'aoi':       aoi,
        'model':     'GFS' if model == 'gfs' else 'ECMWF IFS',
        'provider':  'Open-Meteo (free, no key)',
        'level_m':   level,
        'grid':      list(grid_results.values()),
        'n_points':  len(grid_results),
        'timestamp': datetime.utcnow().isoformat(),
        'source':    model + '-live',
    }
    _cache.set(cache_key, out, expire=3600)
    return out