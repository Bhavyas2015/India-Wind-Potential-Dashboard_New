import httpx
import asyncio
import diskcache
import logging
from collections import defaultdict
from datetime import datetime
import numpy as np

logger = logging.getLogger('windsite.era5')
BASE = 'https://archive-api.open-meteo.com/v1/archive'


def _monthly(dates, ws, wd, t):
    wb, db, tb = defaultdict(list), defaultdict(list), defaultdict(list)
    for dt, w, d, tmp in zip(dates, ws, wd, t):
        try:
            x = datetime.strptime(dt, '%Y-%m-%d')
            k = (x.year, x.month)
            if w and w > 0:
                wb[k].append(w)
            if d and d > -900:
                db[k].append(d)
            if tmp and tmp > -90:
                tb[k].append(tmp)
        except Exception:
            pass
    mo = sorted(wb.keys())
    return (
        [round(float(np.mean(wb[m])), 3) for m in mo],
        [round(float(np.mean(db.get(m, [225]))), 1) for m in mo],
        [round(float(np.mean(tb.get(m, [25]))), 2) for m in mo]
    )


async def fetch(la, lo, s, e, cache_dir='data/cache/era5'):
    c = diskcache.Cache(cache_dir)
    k = 'era5_{:.2f}_{:.2f}_{}_{}'.format(la, lo, s, e)
    hit = c.get(k)
    if hit:
        return dict(hit, source='era5-cached')
    url = (BASE + '?latitude={:.4f}&longitude={:.4f}'.format(la, lo)
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
                raise ValueError('too few')
            res = {'ws10': ws, 'wd10': wd, 't2m': t, 'ps_hpa': 1013.25, 'n_months': len(ws)}
            c.set(k, res, expire=86400 * 30)
            return dict(res, source='era5')
        except Exception as ex:
            logger.warning('ERA5 att {}: {}'.format(att + 1, ex))
            if att < 2:
                await asyncio.sleep(2 ** att)
    raise RuntimeError('ERA5 failed ({},{})'.format(la, lo))