import asyncio
import logging
from pathlib import Path
from app.services.nasa_power import fetch as nasa_fetch
from app.services.era5_client import fetch as era5_fetch

logger = logging.getLogger('windsite.orch')


async def fetch_point(la, lo, s, e, cache_base='data/cache'):
    for fn, nm in [(nasa_fetch, 'NASA'), (era5_fetch, 'ERA5')]:
        try:
            return await fn(la, lo, s, e, cache_dir=str(Path(cache_base) / nm.lower()))
        except Exception as ex:
            logger.info('{} failed ({},{}): {}'.format(nm, la, lo, ex))
    raise RuntimeError('All sources failed ({},{})'.format(la, lo))


async def fetch_grid(pts, s, e, max_con=6, cache_base='data/cache', cb=None):
    sem = asyncio.Semaphore(max_con)
    results = [None] * len(pts)
    stats = {'nasa': 0, 'era5': 0, 'cached': 0, 'errors': 0}
    done = [0]

    async def one(i, la, lo):
        async with sem:
            try:
                r = await fetch_point(la, lo, s, e, cache_base)
                src = r.get('source', '')
                if 'cached' in src:
                    stats['cached'] += 1
                elif 'nasa' in src:
                    stats['nasa'] += 1
                elif 'era5' in src:
                    stats['era5'] += 1
                results[i] = r
            except Exception as ex:
                stats['errors'] += 1
                results[i] = {'lat': la, 'lon': lo, 'ws10': [], 'wd10': [], 't2m': [], 'source': 'error', 'error': str(ex)}
            done[0] += 1
            if cb:
                cb(done[0], len(pts))

    await asyncio.gather(*[one(i, la, lo) for i, (la, lo) in enumerate(pts)])
    return results, stats