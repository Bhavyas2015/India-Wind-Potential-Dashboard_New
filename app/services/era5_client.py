import httpx
import asyncio
import diskcache
import logging
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger('windsite.era5')
BASE_DAILY   = 'https://archive-api.open-meteo.com/v1/archive'
BASE_HOURLY  = 'https://api.open-meteo.com/v1/forecast'


def _monthly(dates, ws, wd, t):
    wb, db, tb = defaultdict(list), defaultdict(list), defaultdict(list)
    for dt, w, d, tmp in zip(dates, ws, wd, t):
        try:
            x = datetime.strptime(dt, '%Y-%m-%d')
            k = (x.year, x.month)
            if w and w > 0:   wb[k].append(w)
            if d and d > -900: db[k].append(d)
            if tmp and tmp > -90: tb[k].append(tmp)
        except Exception:
            pass
    mo = sorted(wb.keys())
    return (
        [round(float(np.mean(wb[m])), 3) for m in mo],
        [round(float(np.mean(db.get(m, [225]))), 1) for m in mo],
        [round(float(np.mean(tb.get(m, [25]))), 2) for m in mo]
    )


async def fetch(la, lo, s, e, cache_dir='data/cache/era5'):
    """Fetch monthly ERA5 data for historical analysis."""
    c = diskcache.Cache(cache_dir)
    k = 'era5_{:.2f}_{:.2f}_{}_{}'.format(la, lo, s, e)
    hit = c.get(k)
    if hit:
        return dict(hit, source='era5-cached')
    url = (BASE_DAILY
           + '?latitude={:.4f}&longitude={:.4f}'.format(la, lo)
           + '&start_date={}-01-01&end_date={}-12-31'.format(s, e)
           + '&daily=wind_speed_10m_mean,wind_direction_10m_dominant,temperature_2m_mean'
           + '&wind_speed_unit=ms&timezone=auto')
    for att in range(3):
        try:
            await asyncio.sleep(0.25)
            async with httpx.AsyncClient(timeout=45) as cl:
                r = await cl.get(url)
                r.raise_for_status()
                d = r.json()
            dy = d.get('daily', {})
            ws, wd, t = _monthly(
                dy.get('time', []),
                dy.get('wind_speed_10m_mean', []),
                dy.get('wind_direction_10m_dominant', []),
                dy.get('temperature_2m_mean', [])
            )
            if len(ws) < 12:
                raise ValueError('too few months')
            res = {'ws10': ws, 'wd10': wd, 't2m': t,
                   'ps_hpa': 1013.25, 'n_months': len(ws)}
            c.set(k, res, expire=86400 * 30)
            return dict(res, source='era5')
        except Exception as ex:
            logger.warning('ERA5 att {}: {}'.format(att + 1, ex))
            if att < 2:
                await asyncio.sleep(2 ** att)
    raise RuntimeError('ERA5 failed ({},{})'.format(la, lo))


async def fetch_date_range(
    lat: float,
    lon: float,
    date_from: str,
    date_to: str,
    cache_dir: str = 'data/cache/era5'
) -> dict:
    """
    Fetch hourly wind data for a specific date range.
    date_from, date_to: 'YYYY-MM-DD' format
    Works for both historical dates and forecast (future dates).
    """
    c = diskcache.Cache(cache_dir)
    k = 'era5_range_{:.2f}_{:.2f}_{}_{}'.format(lat, lon, date_from, date_to)
    hit = c.get(k)
    if hit:
        return dict(hit, source='cached')

    # Decide which API to use
    today = datetime.utcnow().date()
    d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    d_to   = datetime.strptime(date_to,   '%Y-%m-%d').date()

    n_days = (d_to - d_from).days + 1

    if d_to <= today:
        # Historical data
        url = (BASE_DAILY
               + '?latitude={:.4f}&longitude={:.4f}'.format(lat, lon)
               + '&start_date={}&end_date={}'.format(date_from, date_to)
               + '&hourly=wind_speed_10m,wind_direction_10m,'
               + 'wind_speed_80m,wind_direction_80m,'
               + 'wind_gusts_10m,temperature_2m'
               + '&wind_speed_unit=ms&timezone=UTC')
        source_tag = 'era5-historical'
    else:
        # Forecast data (future dates)
        url = (BASE_HOURLY
               + '?latitude={:.4f}&longitude={:.4f}'.format(lat, lon)
               + '&hourly=wind_speed_10m,wind_direction_10m,'
               + 'wind_speed_80m,wind_direction_80m,'
               + 'wind_gusts_10m,temperature_2m'
               + '&wind_speed_unit=ms'
               + '&forecast_days={}'.format(min(n_days + 1, 16))
               + '&timezone=UTC')
        source_tag = 'gfs-forecast'

    try:
        async with httpx.AsyncClient(timeout=30.0) as cl:
            r = await cl.get(url)
            r.raise_for_status()
            d = r.json()

        h = d.get('hourly', {})
        times = h.get('time', [])

        # Filter to exact date range
        def in_range(t):
            try:
                dt = datetime.strptime(t[:10], '%Y-%m-%d').date()
                return d_from <= dt <= d_to
            except Exception:
                return False

        indices = [i for i, t in enumerate(times) if in_range(t)]

        def extract(key):
            arr = h.get(key, [])
            return [arr[i] for i in indices if i < len(arr)]

        ws10  = extract('wind_speed_10m')
        wd10  = extract('wind_direction_10m')
        ws80  = extract('wind_speed_80m')
        wd80  = extract('wind_direction_80m')
        gusts = extract('wind_gusts_10m')
        temp  = extract('temperature_2m')
        t_filtered = [times[i] for i in indices]

        if not ws10:
            raise ValueError('No data for date range')

        # Summary stats
        ws10_clean = [v for v in ws10 if v is not None and v > 0]
        ws80_clean = [v for v in ws80 if v is not None and v > 0]

        result = {
            'lat':        lat,
            'lon':        lon,
            'date_from':  date_from,
            'date_to':    date_to,
            'n_days':     n_days,
            'n_hours':    len(t_filtered),
            'times':      t_filtered,
            'ws10':       ws10,
            'wd10':       wd10,
            'ws80':       ws80,
            'wd80':       wd80,
            'gusts':      gusts,
            'temp':       temp,
            'stats': {
                'mean_ws10':  round(float(np.mean(ws10_clean)), 3) if ws10_clean else 0,
                'max_ws10':   round(float(np.max(ws10_clean)), 3)  if ws10_clean else 0,
                'min_ws10':   round(float(np.min(ws10_clean)), 3)  if ws10_clean else 0,
                'mean_ws80':  round(float(np.mean(ws80_clean)), 3) if ws80_clean else 0,
                'max_ws80':   round(float(np.max(ws80_clean)), 3)  if ws80_clean else 0,
                'calm_hrs':   sum(1 for v in ws10_clean if v < 1.0),
                'strong_hrs': sum(1 for v in ws10_clean if v > 10.0),
            },
            'source': source_tag,
        }

        # Cache for 1 hour if forecast, 24 hours if historical
        expire = 3600 if source_tag == 'gfs-forecast' else 86400
        c.set(k, result, expire=expire)
        return result

    except Exception as e:
        logger.error('Date range fetch failed: {}'.format(e))
        raise RuntimeError('Date range fetch failed: {}'.format(str(e)))


async def fetch_date_range_batch(
    points: list,
    date_from: str,
    date_to: str,
    max_concurrent: int = 5,
    cache_dir: str = 'data/cache/era5'
) -> dict:
    """Fetch date range data for multiple points."""
    sem = asyncio.Semaphore(max_concurrent)
    results = {}

    async def one(lat, lon):
        async with sem:
            await asyncio.sleep(0.2)
            try:
                results[(lat, lon)] = await fetch_date_range(
                    lat, lon, date_from, date_to, cache_dir)
            except Exception as e:
                results[(lat, lon)] = {
                    'lat': lat, 'lon': lon,
                    'error': str(e), 'source': 'error',
                    'ws10': [], 'wd10': [], 'times': []
                }

    await asyncio.gather(*[one(la, lo) for la, lo in points])
    return results