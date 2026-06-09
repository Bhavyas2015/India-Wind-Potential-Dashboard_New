import httpx
import asyncio
import diskcache
import logging

logger = logging.getLogger('windsite.nasa')
BASE = 'https://power.larc.nasa.gov/api/temporal/monthly/point'
PARAMS = 'WS10M,WD10M,T2M,PS'


def _key(la, lo, s, e):
    return 'nasa_{:.2f}_{:.2f}_{}_{}'.format(la, lo, s, e)


def _url(la, lo, s, e):
    return (BASE + '?parameters=' + PARAMS + '&community=RE'
            + '&longitude={:.4f}&latitude={:.4f}'.format(lo, la)
            + '&start={}&end={}&format=JSON'.format(s, e))


def _parse(d):
    p = d['properties']['parameter']
    ws = [v for v in p['WS10M'].values() if v > -900]
    wd = [v for v in p.get('WD10M', {}).values() if v > -900]
    t = [v for v in p['T2M'].values() if v > -900]
    ps = [v for v in p.get('PS', {}).values() if v > -900]
    return {
        'ws10': ws, 'wd10': wd, 't2m': t,
        'ps_hpa': round(sum(ps) / len(ps), 2) if ps else 1013.25,
        'n_months': len(ws)
    }


async def fetch(la, lo, s, e, cache_dir='data/cache/nasa'):
    c = diskcache.Cache(cache_dir)
    k = _key(la, lo, s, e)
    hit = c.get(k)
    if hit:
        return dict(hit, source='nasa-cached')
    for att in range(3):
        await asyncio.sleep(0.4)
        try:
            async with httpx.AsyncClient(timeout=30) as cl:
                r = await cl.get(_url(la, lo, s, e))
                r.raise_for_status()
                d = r.json()
            ws = [v for v in d['properties']['parameter']['WS10M'].values() if v > -900]
            if len(ws) < 12:
                raise ValueError('too few months')
            res = _parse(d)
            c.set(k, res, expire=86400 * 30)
            return dict(res, source='nasa-power')
        except Exception as ex:
            logger.warning('NASA att {}: {}'.format(att + 1, ex))
            if att < 2:
                await asyncio.sleep(2 ** att)
    raise RuntimeError('NASA failed ({},{})'.format(la, lo))


async def fetch_batch(pts, s, e, max_con=5, cache_dir='data/cache/nasa'):
    sem = asyncio.Semaphore(max_con)

    async def one(la, lo):
        async with sem:
            try:
                return await fetch(la, lo, s, e, cache_dir)
            except Exception as ex:
                return {'lat': la, 'lon': lo, 'ws10': [], 'wd10': [], 't2m': [], 'source': 'error', 'error': str(ex)}

    return list(await asyncio.gather(*[one(la, lo) for la, lo in pts]))