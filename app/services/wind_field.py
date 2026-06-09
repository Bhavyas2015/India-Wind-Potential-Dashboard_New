import httpx
import asyncio
import diskcache
import math
import logging
from datetime import datetime

logger = logging.getLogger('windsite.windfield')

GFS_URL = 'https://api.open-meteo.com/v1/forecast'

AOI_BOUNDS = {
    'gujarat':     {'lat_min': 20.0, 'lat_max': 25.5, 'lon_min': 68.0, 'lon_max': 75.5},
    'rajasthan':   {'lat_min': 23.5, 'lat_max': 31.5, 'lon_min': 69.0, 'lon_max': 78.5},
    'tamilnadu':   {'lat_min':  7.5, 'lat_max': 14.0, 'lon_min': 76.5, 'lon_max': 81.0},
    'maharashtra': {'lat_min': 15.0, 'lat_max': 22.5, 'lon_min': 72.5, 'lon_max': 80.5},
    'andhra':      {'lat_min': 11.5, 'lat_max': 19.5, 'lon_min': 77.5, 'lon_max': 84.5},
    'karnataka':   {'lat_min': 11.5, 'lat_max': 18.5, 'lon_min': 74.0, 'lon_max': 79.0},
}

_cache = diskcache.Cache('data/cache/wind_now')


def _grid_points(bounds, step=0.5):
    lats = [round(bounds['lat_min'] + i * step, 2)
            for i in range(int((bounds['lat_max'] - bounds['lat_min']) / step) + 1)]
    lons = [round(bounds['lon_min'] + i * step, 2)
            for i in range(int((bounds['lon_max'] - bounds['lon_min']) / step) + 1)]
    return [(la, lo) for la in lats for lo in lons]


async def fetch_live_wind_grid(aoi='gujarat', levels=None):
    if levels is None:
        levels = [10, 80]
    bounds = AOI_BOUNDS.get(aoi, AOI_BOUNDS['gujarat'])
    cache_key = 'live_{}_{}'.format(aoi, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit is not None:
        return dict(hit, source='gfs-cached')

    pts = _grid_points(bounds, step=0.5)
    sem = asyncio.Semaphore(8)
    results = {}

    async def fetch_pt(lat, lon):
        async with sem:
            try:
                await asyncio.sleep(0.05)
                params = {
                    'latitude': lat, 'longitude': lon,
                    'hourly': 'wind_speed_10m,wind_direction_10m,wind_speed_80m,wind_direction_80m',
                    'wind_speed_unit': 'ms',
                    'forecast_days': 1,
                    'format': 'json'
                }
                async with httpx.AsyncClient(timeout=20.0) as cl:
                    r = await cl.get(GFS_URL, params=params)
                    r.raise_for_status()
                    d = r.json()
                h = d.get('hourly', {})
                now_h = datetime.utcnow().hour
                ws10_arr = h.get('wind_speed_10m', [])
                wd10_arr = h.get('wind_direction_10m', [])
                ws80_arr = h.get('wind_speed_80m', [])
                wd80_arr = h.get('wind_direction_80m', [])
                ws10 = ws10_arr[now_h] if len(ws10_arr) > now_h else 5.0
                wd10 = wd10_arr[now_h] if len(wd10_arr) > now_h else 225.0
                ws80 = ws80_arr[now_h] if len(ws80_arr) > now_h else 7.0
                wd80 = wd80_arr[now_h] if len(wd80_arr) > now_h else 225.0
                rad80 = math.radians(wd80)
                results[(lat, lon)] = {
                    'lat': lat, 'lon': lon,
                    'ws10m': round(ws10, 2), 'wd10m': round(wd10, 1),
                    'ws80m': round(ws80, 2), 'wd80m': round(wd80, 1),
                    'u80m': round(-ws80 * math.sin(rad80), 3),
                    'v80m': round(-ws80 * math.cos(rad80), 3),
                }
            except Exception as e:
                logger.warning('GFS pt ({},{}) failed: {}'.format(lat, lon, e))
                results[(lat, lon)] = {
                    'lat': lat, 'lon': lon,
                    'ws10m': 5.0, 'wd10m': 225.0,
                    'ws80m': 7.0, 'wd80m': 225.0,
                    'u80m': -5.0, 'v80m': -5.0,
                }

    await asyncio.gather(*[fetch_pt(la, lo) for la, lo in pts])
    grid = list(results.values())
    out = {
        'grid': grid,
        'aoi': aoi,
        'n_points': len(grid),
        'timestamp': datetime.utcnow().isoformat(),
        'model': 'GFS via Open-Meteo',
        'source': 'gfs-live',
    }
    _cache.set(cache_key, out, expire=3600)
    return out


async def fetch_wind_timeseries(lat, lon, hours=48):
    cache_key = 'ts_{:.2f}_{:.2f}_{}'.format(lat, lon, datetime.utcnow().strftime('%Y%m%d_%H'))
    hit = _cache.get(cache_key)
    if hit:
        return dict(hit, source='cached')
    try:
        params = {
            'latitude': lat, 'longitude': lon,
            'hourly': 'wind_speed_10m,wind_direction_10m,wind_speed_80m,wind_gusts_10m,temperature_2m',
            'wind_speed_unit': 'ms',
            'forecast_days': min(int(math.ceil(hours / 24)) + 1, 7),
            'format': 'json'
        }
        async with httpx.AsyncClient(timeout=20.0) as cl:
            r = await cl.get(GFS_URL, params=params)
            r.raise_for_status()
            d = r.json()
        h = d.get('hourly', {})
        out = {
            'lat': lat, 'lon': lon,
            'times': h.get('time', [])[:hours],
            'ws10': h.get('wind_speed_10m', [])[:hours],
            'wd10': h.get('wind_direction_10m', [])[:hours],
            'ws80': h.get('wind_speed_80m', [])[:hours],
            'gusts': h.get('wind_gusts_10m', [])[:hours],
            'temp': h.get('temperature_2m', [])[:hours],
            'source': 'gfs-live',
            'model': 'GFS via Open-Meteo',
        }
        _cache.set(cache_key, out, expire=3600)
        return out
    except Exception as e:
        raise RuntimeError('GFS timeseries failed: {}'.format(e))