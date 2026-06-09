from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional
from datetime import datetime
import asyncio
import numpy as np
import json
import io
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.physics.wind_physics import build_point, TURBINES
from app.services.orchestrator import fetch_grid, fetch_point as orch_fetch_pt
from app.services.wind_field import fetch_live_wind_grid, fetch_wind_timeseries
from app.gis.terrain import TerrainClient
from app.gis.lulc_client import LULCClient
from app.mcda.scoring import MCDAEngine, MCDAConstraints, ahp_weights
from app.finance.model import compute_finance

app = FastAPI(title='WindSite India v4', version='4.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*']
)

_sess = {}

AOI = {
    'gujarat':     {'bounds': [[20.5, 68.0], [25.5, 75.0]], 'label': 'Gujarat Plains', 'state': 'Gujarat'},
    'rajasthan':   {'bounds': [[24.0, 69.0], [31.0, 78.0]], 'label': 'Rajasthan Corridor', 'state': 'Rajasthan'},
    'tamilnadu':   {'bounds': [[8.0, 77.0], [14.0, 80.5]], 'label': 'Tamil Nadu Coast', 'state': 'Tamil Nadu'},
    'maharashtra': {'bounds': [[15.5, 72.5], [22.0, 80.0]], 'label': 'Maharashtra Plateau', 'state': 'Maharashtra'},
    'andhra':      {'bounds': [[12.0, 78.0], [19.0, 84.0]], 'label': 'Andhra Pradesh', 'state': 'Andhra'},
    'karnataka':   {'bounds': [[12.0, 74.5], [18.0, 78.5]], 'label': 'Karnataka Deccan', 'state': 'Karnataka'},
}


class AnalysisReq(BaseModel):
    aoi:          str   = Field('gujarat')
    start_year:   int   = Field(2020, ge=2001, le=2025)
    end_year:     int   = Field(2023, ge=2001, le=2025)
    grid_spacing: float = Field(0.5, ge=0.25, le=1.0)
    hub_height:   float = Field(80.0, ge=10.0, le=200.0)
    alpha:        float = Field(0.143, ge=0.05, le=0.5)
    turbine:      str   = Field('vestas_v90')
    ahp_raw:      Dict  = Field(default_factory=lambda: {'wind': 5, 'land': 4, 'ter': 3, 'acc': 4, 'fin': 3})
    max_slope:    float = Field(15.0, ge=3.0, le=35.0)
    buffer_m:     float = Field(500.0, ge=0, le=3000.0)
    max_grid_km:  float = Field(30.0, ge=5.0, le=100.0)
    min_wind_ms:  float = Field(4.0, ge=2.0, le=8.0)
    excl_forest:  bool  = True
    excl_water:   bool  = True
    excl_prot:    bool  = True
    ppa_override: Optional[float] = None
    dr:           float = Field(0.10, ge=0.05, le=0.25)
    lt:           int   = Field(25, ge=10, le=30)

    @validator('end_year')
    def ey(cls, v, values):
        if 'start_year' in values and v < values['start_year']:
            raise ValueError('end >= start')
        return v

    @validator('turbine')
    def tv(cls, v):
        if v not in TURBINES:
            raise ValueError('unknown turbine')
        return v


async def _run(req):
    b = AOI[req.aoi]['bounds']
    state = AOI[req.aoi]['state']
    lats = np.arange(b[0][0], b[1][0] + req.grid_spacing / 2, req.grid_spacing)
    lons = np.arange(b[0][1], b[1][1] + req.grid_spacing / 2, req.grid_spacing)
    pts = [(round(float(la), 4), round(float(lo), 4)) for la in lats for lo in lons]
    tc = TerrainClient(cache_dir='data/cache/terrain')
    lc = LULCClient(cache_dir='data/cache/lulc')
    elevs = await tc.batch_elev(pts)
    wind, stats = await fetch_grid(pts, req.start_year, req.end_year, cache_base='data/cache')
    grid = []
    for (la, lo), raw in zip(pts, wind):
        if not raw or not raw.get('ws10') or raw.get('source') == 'error':
            continue
        e = float(elevs.get((la, lo)) or 0)
        ph = build_point(la, lo, raw['ws10'], raw['t2m'], req.hub_height, req.alpha,
                         req.turbine, raw['source'], e, raw.get('wd10', []))
        tr = await tc.full(la, lo, elevs, req.grid_spacing, req.buffer_m, lc)
        fin = compute_finance(ph['cf'], ph['wb']['c'], req.turbine, state, TURBINES,
                              req.ppa_override, req.dr, req.lt)
        ph['lcoe_inr_kwh'] = fin.get('lcoe_inr_kwh')
        grid.append({**ph, **tr, 'finance': fin})
    ahp_w, cr, cr_ok = ahp_weights(req.ahp_raw)
    eng = MCDAEngine(req.ahp_raw, MCDAConstraints(
        max_slope=req.max_slope, buffer_m=req.buffer_m,
        max_grid_km=req.max_grid_km, min_wind_ms=req.min_wind_ms,
        excl_forest=req.excl_forest, excl_water=req.excl_water, excl_prot=req.excl_prot))
    scores = eng.score(grid)
    summ = eng.summary(grid, scores, req.grid_spacing)
    for pt, sc in zip(grid, scores):
        pt['mcda'] = sc
    return {'grid': grid, 'summary': summ, 'source_stats': stats,
            'aoi': req.aoi, 'state': state, 'n_points': len(grid),
            'ahp_cr': cr, 'ahp_cr_ok': cr_ok,
            'generated': datetime.utcnow().isoformat()}


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '4.0.0', 'ts': datetime.utcnow().isoformat()}


@app.get('/api/meta')
def meta():
    now = datetime.utcnow()
    return {'aoi': AOI, 'turbines': TURBINES,
            'current_year': now.year,
            'nasa_max_year': now.year - 1 if now.month < 6 else now.year}


@app.post('/api/analysis')
async def analysis(req: AnalysisReq):
    try:
        res = await _run(req)
        sid = '{}_{}'.format(req.aoi, datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
        _sess[sid] = res
        res['session_id'] = sid
        return JSONResponse(content=res)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get('/api/wind/live')
async def wind_live(aoi: str = 'gujarat'):
    try:
        return await fetch_live_wind_grid(aoi, [10, 80])
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get('/api/wind/timeseries')
async def wind_ts(lat: float, lon: float, hours: int = 48):
    try:
        return await fetch_wind_timeseries(lat, lon, hours)
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get('/api/point')
async def single_point(lat: float, lon: float,
                       start_year: int = 2020, end_year: int = 2023,
                       hub_height: float = 80.0, alpha: float = 0.143,
                       turbine: str = 'vestas_v90'):
    try:
        raw = await orch_fetch_pt(lat, lon, start_year, end_year)
        tc = TerrainClient(cache_dir='data/cache/terrain')
        elevs = await tc.batch_elev([(lat, lon)])
        e = float(elevs.get((lat, lon)) or 0)
        pt = build_point(lat, lon, raw['ws10'], raw['t2m'],
                         hub_height, alpha, turbine, raw['source'], e, raw.get('wd10', []))
        lc = LULCClient(cache_dir='data/cache/lulc')
        tr = await tc.full(lat, lon, elevs, 0.5, 500, lc)
        return {**pt, **tr}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get('/api/export/geojson/{sid}')
def export_gj(sid: str, min_suit: float = 0.0):
    if sid not in _sess:
        raise HTTPException(404, 'not found')
    d = _sess[sid]
    h = 0.25
    feats = [
        {'type': 'Feature',
         'geometry': {'type': 'Polygon', 'coordinates': [[[p['lon'] - h, p['lat'] - h], [p['lon'] + h, p['lat'] - h], [p['lon'] + h, p['lat'] + h], [p['lon'] - h, p['lat'] + h], [p['lon'] - h, p['lat'] - h]]]},
         'properties': {k: v for k, v in p.items() if k not in ['wsHub', 'ws10', 'monthlyMeans']}}
        for p in d['grid'] if p.get('mcda', {}).get('s', -1) >= min_suit
    ]
    gj = {'type': 'FeatureCollection',
          'metadata': {'generated': datetime.utcnow().isoformat(), 'n': len(feats)},
          'features': feats}
    return StreamingResponse(
        io.StringIO(json.dumps(gj, indent=2)),
        media_type='application/geo+json',
        headers={'Content-Disposition': 'attachment; filename=windsite_{}.geojson'.format(sid)})


@app.get('/api/export/csv/{sid}')
def export_csv(sid: str):
    if sid not in _sess:
        raise HTTPException(404, 'not found')
    d = _sess[sid]
    out = io.StringIO()
    fields = ['lat', 'lon', 'meanWS', 'wpd', 'cf', 'aep', 'lcoe_inr_kwh',
              'elev_m', 'slope', 'lulc', 'lulc_src', 'esa_code',
              'gridDist', 'iec_cls', 'nrel_cls', 'dataSource',
              'mcda_score', 'mcda_cls', 'irr_pct', 'payback_yr', 'npv_cr']
    w = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    for p in d['grid']:
        mc = p.get('mcda', {})
        fi = p.get('finance', {})
        w.writerow({**p,
                    'mcda_score': mc.get('s', ''), 'mcda_cls': mc.get('cls', ''),
                    'irr_pct': fi.get('irr_pct', ''), 'payback_yr': fi.get('payback_yr', ''),
                    'npv_cr': fi.get('npv_cr', '')})
    out.seek(0)
    return StreamingResponse(
        out, media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=windsite_{}.csv'.format(sid)})
# ── NEW ENDPOINTS ──────────────────────────────────────────────────────────

# Wind Rose
@app.get('/api/wind_rose')
async def wind_rose_endpoint(lat: float, lon: float,
                              start_year: int = 2020, end_year: int = 2023):
    try:
        from app.services.wind_rose import compute_wind_rose, wind_rose_to_chartjs
        raw = await orch_fetch_pt(lat, lon, start_year, end_year)
        rose = compute_wind_rose(raw.get('ws10', []), raw.get('wd10', []))
        return {'rose': rose, 'chartjs': wind_rose_to_chartjs(rose), 'lat': lat, 'lon': lon}
    except Exception as e:
        raise HTTPException(502, str(e))


# Wake Loss Model
@app.post('/api/wake_loss')
async def wake_loss_endpoint(payload: dict):
    try:
        from app.services.wake_loss import farm_aep_with_wake
        turbines  = payload.get('turbines', [])
        wb_k      = payload.get('weibull_k', 2.0)
        wb_c      = payload.get('weibull_c', 7.0)
        wind_rose = payload.get('wind_rose', None)
        decay_k   = payload.get('wake_decay_k', 0.075)
        return farm_aep_with_wake(turbines, wb_k, wb_c, wind_rose, decay_k)
    except Exception as e:
        raise HTTPException(500, str(e))


# Farm Layout Optimizer
@app.post('/api/farm_layout')
async def farm_layout_endpoint(payload: dict):
    try:
        from app.services.farm_layout import optimize_layout
        return optimize_layout(
            center_lat     = payload.get('lat', 22.8),
            center_lon     = payload.get('lon', 71.5),
            turbine_config = payload.get('turbine_config', {}),
            weibull_k      = payload.get('weibull_k', 2.0),
            weibull_c      = payload.get('weibull_c', 7.0),
            wind_rose      = payload.get('wind_rose', None),
            max_turbines   = payload.get('max_turbines', 20),
            area_km2       = payload.get('area_km2', 10.0),
        )
    except Exception as e:
        raise HTTPException(500, str(e))


# PDF Report
@app.get('/api/export/pdf/{sid}')
async def export_pdf(sid: str):
    if sid not in _sess:
        raise HTTPException(404, 'Session not found')
    try:
        from app.reports.pdf_report import generate_pdf_report
        pdf_bytes = generate_pdf_report(_sess[sid])
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename=windsite_{}.pdf'.format(sid)}
        )
    except Exception as e:
        raise HTTPException(500, str(e))


# OSM Grid Distance
@app.get('/api/grid_distance')
async def grid_distance_endpoint(lat: float, lon: float,
                                  voltage_min: int = 66000,
                                  radius_km: float = 80.0):
    try:
        from app.gis.osm_grid import nearest_grid_distance
        return await nearest_grid_distance(lat, lon, voltage_min, radius_km)
    except Exception as e:
        raise HTTPException(502, str(e))


# Regulatory Compliance
@app.get('/api/regulatory')
async def regulatory_endpoint(lat: float, lon: float):
    try:
        from app.gis.regulatory import check_regulatory_compliance, check_osm_protected_areas
        compliance = check_regulatory_compliance(lat, lon)
        osm_areas  = await check_osm_protected_areas(lat, lon)
        return {**compliance, 'osm_data': osm_areas}
    except Exception as e:
        raise HTTPException(502, str(e))


# GFS Real-time Wind
@app.get('/api/wind/gfs')
async def wind_gfs(lat: float, lon: float):
    try:
        from app.services.gfs_realtime import fetch_gfs_current
        return await fetch_gfs_current(lat, lon)
    except Exception as e:
        raise HTTPException(502, str(e))


# ECMWF Real-time Wind
@app.get('/api/wind/ecmwf')
async def wind_ecmwf(lat: float, lon: float):
    try:
        from app.services.gfs_realtime import fetch_ecmwf_current
        return await fetch_ecmwf_current(lat, lon)
    except Exception as e:
        raise HTTPException(502, str(e))


# GFS + ECMWF Model Comparison
@app.get('/api/wind/compare')
async def wind_compare(lat: float, lon: float):
    try:
        from app.services.gfs_realtime import fetch_model_comparison
        return await fetch_model_comparison(lat, lon)
    except Exception as e:
        raise HTTPException(502, str(e))


# Real-time Wind Grid (powers animation)
@app.get('/api/wind/grid')
async def wind_grid(aoi: str = 'gujarat', model: str = 'gfs', level: int = 80):
    try:
        from app.services.gfs_realtime import fetch_wind_grid_realtime
        return await fetch_wind_grid_realtime(aoi, model, level)
    except Exception as e:
        raise HTTPException(502, str(e))


# Enhanced LULC
@app.get('/api/lulc')
async def lulc_endpoint(lat: float, lon: float, elev: float = 0.0):
    try:
        from app.gis.lulc_enhanced import classify_enhanced
        return await classify_enhanced(lat, lon, elev)
    except Exception as e:
        raise HTTPException(502, str(e))


# All new endpoints summary
@app.get('/api/endpoints')
def list_endpoints():
    return {
        'new_endpoints': [
            'GET  /api/wind_rose?lat=&lon=',
            'POST /api/wake_loss',
            'POST /api/farm_layout',
            'GET  /api/export/pdf/{sid}',
            'GET  /api/grid_distance?lat=&lon=',
            'GET  /api/regulatory?lat=&lon=',
            'GET  /api/wind/gfs?lat=&lon=',
            'GET  /api/wind/ecmwf?lat=&lon=',
            'GET  /api/wind/compare?lat=&lon=',
            'GET  /api/wind/grid?aoi=&model=&level=',
            'GET  /api/lulc?lat=&lon=',
        ]
    }
# Date-specific wind data endpoint
@app.get('/api/wind/daterange')
async def wind_date_range(
    lat:       float,
    lon:       float,
    date_from: str = '',
    date_to:   str = ''
):
    """
    Fetch hourly wind data for a specific date range.
    date_from, date_to: YYYY-MM-DD format
    Works for historical dates and future forecast.
    """
    try:
        from app.services.era5_client import fetch_date_range
        from datetime import datetime, timedelta

        # Default to last 2 days if no dates provided
        if not date_from or not date_to:
            today = datetime.utcnow().date()
            date_to   = str(today)
            date_from = str(today - timedelta(days=1))

        # Validate date format
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to,   '%Y-%m-%d')
        except ValueError:
            raise HTTPException(400, 'Invalid date format. Use YYYY-MM-DD')

        # Max 30 days per request
        d1 = datetime.strptime(date_from, '%Y-%m-%d')
        d2 = datetime.strptime(date_to,   '%Y-%m-%d')
        if (d2 - d1).days > 30:
            raise HTTPException(400, 'Max date range is 30 days')
        if d2 < d1:
            raise HTTPException(400, 'date_to must be >= date_from')

        return await fetch_date_range(lat, lon, date_from, date_to)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


# Date range grid analysis
@app.post('/api/wind/daterange/grid')
async def wind_date_range_grid(payload: dict):
    """
    Fetch date range wind data for multiple grid points.
    Useful for short-term wind resource assessment.
    """
    try:
        from app.services.era5_client import fetch_date_range_batch
        from datetime import datetime

        points    = payload.get('points', [])
        date_from = payload.get('date_from', '')
        date_to   = payload.get('date_to',   '')

        if not points:
            raise HTTPException(400, 'No points provided')
        if not date_from or not date_to:
            raise HTTPException(400, 'date_from and date_to required')

        pts = [(p['lat'], p['lon']) for p in points]
        results = await fetch_date_range_batch(pts, date_from, date_to)

        return {
            'date_from': date_from,
            'date_to':   date_to,
            'n_points':  len(pts),
            'results': [
                results.get((p['lat'], p['lon']), {})
                for p in points
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))