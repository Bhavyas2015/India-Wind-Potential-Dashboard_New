"""
WindSite India v4 - Multi-Turbine Farm Layout Optimizer
Optimizes turbine spacing for maximum AEP with minimum wake losses.
Uses grid and staggered layout patterns with Jensen wake model.
"""
import math
import numpy as np
from typing import List, Dict, Tuple, Optional


def generate_grid_layout(
    center_lat: float,
    center_lon: float,
    n_rows: int,
    n_cols: int,
    spacing_x_d: float,
    spacing_y_d: float,
    rotor_d_m: float,
    wind_direction_deg: float = 225.0,
    rotation_deg: float = 0.0
) -> List[Dict]:
    """
    Generate regular grid turbine layout aligned with wind direction.

    Parameters:
        center_lat/lon:    farm center coordinates
        n_rows/n_cols:     grid dimensions
        spacing_x_d:       downwind spacing in rotor diameters
        spacing_y_d:       crosswind spacing in rotor diameters
        rotor_d_m:         rotor diameter in metres
        wind_direction_deg: prevailing wind direction
        rotation_deg:      additional rotation from North

    Returns:
        list of turbine position dicts with lat, lon, row, col
    """
    spacing_x_m = spacing_x_d * rotor_d_m
    spacing_y_m = spacing_y_d * rotor_d_m

    align_deg = wind_direction_deg + rotation_deg
    align_rad = math.radians(align_deg)

    m_per_lat = 111000.0
    m_per_lon = 111000.0 * math.cos(math.radians(center_lat))

    turbines = []
    for row in range(n_rows):
        for col in range(n_cols):
            x_offset = (col - (n_cols - 1) / 2) * spacing_y_m
            y_offset = (row - (n_rows - 1) / 2) * spacing_x_m

            # Rotate to align with wind
            dx = x_offset * math.cos(align_rad) - y_offset * math.sin(align_rad)
            dy = x_offset * math.sin(align_rad) + y_offset * math.cos(align_rad)

            lat = center_lat + dy / m_per_lat
            lon = center_lon + dx / m_per_lon

            turbines.append({
                'id':    'T{:02d}{:02d}'.format(row, col),
                'row':   row,
                'col':   col,
                'lat':   round(lat, 6),
                'lon':   round(lon, 6),
                'dx_m':  round(dx, 1),
                'dy_m':  round(dy, 1),
            })

    return turbines


def generate_staggered_layout(
    center_lat: float,
    center_lon: float,
    n_rows: int,
    n_cols: int,
    spacing_x_d: float,
    spacing_y_d: float,
    rotor_d_m: float,
    wind_direction_deg: float = 225.0,
    stagger_fraction: float = 0.5
) -> List[Dict]:
    """
    Generate staggered turbine layout to reduce wake losses.
    Alternating rows are offset by stagger_fraction of crosswind spacing.
    """
    spacing_x_m = spacing_x_d * rotor_d_m
    spacing_y_m = spacing_y_d * rotor_d_m
    stagger_m   = stagger_fraction * spacing_y_m

    align_rad = math.radians(wind_direction_deg)
    m_per_lat = 111000.0
    m_per_lon = 111000.0 * math.cos(math.radians(center_lat))

    turbines = []
    for row in range(n_rows):
        stagger = stagger_m if row % 2 == 1 else 0.0
        for col in range(n_cols):
            x_raw = (col - (n_cols - 1) / 2) * spacing_y_m + stagger
            y_raw = (row - (n_rows - 1) / 2) * spacing_x_m

            dx = x_raw * math.cos(align_rad) - y_raw * math.sin(align_rad)
            dy = x_raw * math.sin(align_rad) + y_raw * math.cos(align_rad)

            lat = center_lat + dy / m_per_lat
            lon = center_lon + dx / m_per_lon

            turbines.append({
                'id':    'S{:02d}{:02d}'.format(row, col),
                'row':   row,
                'col':   col,
                'lat':   round(lat, 6),
                'lon':   round(lon, 6),
                'dx_m':  round(dx, 1),
                'dy_m':  round(dy, 1),
                'staggered': row % 2 == 1,
            })

    return turbines


def farm_capacity_mw(n_turbines: int, turbine_cap_kw: float) -> float:
    return round(n_turbines * turbine_cap_kw / 1000.0, 2)


def spacing_recommendation(
    mean_wind_speed: float,
    turbulence_intensity: float = 0.10
) -> Dict:
    """
    IEC 61400-1 based spacing recommendations.
    """
    if mean_wind_speed >= 9:
        dx_d, dy_d = 9.0, 5.0
    elif mean_wind_speed >= 7:
        dx_d, dy_d = 8.0, 4.5
    elif mean_wind_speed >= 5:
        dx_d, dy_d = 7.0, 4.0
    else:
        dx_d, dy_d = 6.0, 3.5

    if turbulence_intensity > 0.15:
        dx_d += 1.0
        dy_d += 0.5

    return {
        'downwind_d':  dx_d,
        'crosswind_d': dy_d,
        'standard':    'IEC 61400-1 Ed.3',
        'note':        'Increase spacing for high turbulence or complex terrain',
    }


def optimize_layout(
    center_lat: float,
    center_lon: float,
    turbine_config: Dict,
    weibull_k: float,
    weibull_c: float,
    wind_rose: Optional[Dict] = None,
    max_turbines: int = 20,
    area_km2: float = 10.0
) -> Dict:
    """
    Compare grid vs staggered layouts and return optimal configuration.

    Parameters:
        turbine_config: dict with capKW, rotor_d, ci, co, curve, ct
        weibull_k/c:    site wind distribution
        wind_rose:      directional distribution (optional)
        max_turbines:   maximum number of turbines to place
        area_km2:       available area in km²

    Returns:
        dict with grid and staggered layouts, AEP comparison, recommendation
    """
    from app.services.wake_loss import farm_aep_with_wake

    rotor_d = turbine_config.get('rotor_d', 90)
    cap_kw  = turbine_config.get('capKW', 2000)

    mean_ws = weibull_c * 0.887  # approx mean from Weibull c
    spacing = spacing_recommendation(mean_ws)

    dx_d = spacing['downwind_d']
    dy_d = spacing['crosswind_d']

    area_side_km = math.sqrt(area_km2)
    spacing_x_km = dx_d * rotor_d / 1000.0
    spacing_y_km = dy_d * rotor_d / 1000.0

    n_rows = max(1, min(int(area_side_km / spacing_x_km), 8))
    n_cols = max(1, min(int(area_side_km / spacing_y_km), 8))
    n_t    = min(n_rows * n_cols, max_turbines)

    if n_rows * n_cols > max_turbines:
        n_cols = max(1, int(math.sqrt(max_turbines)))
        n_rows = max(1, max_turbines // n_cols)

    # Dominant wind direction
    dom_dir = 225.0
    if wind_rose and wind_rose.get('dominant_deg'):
        dom_dir = wind_rose['dominant_deg']

    # Generate both layouts
    grid_pos = generate_grid_layout(
        center_lat, center_lon, n_rows, n_cols,
        dx_d, dy_d, rotor_d, dom_dir
    )
    stag_pos = generate_staggered_layout(
        center_lat, center_lon, n_rows, n_cols,
        dx_d, dy_d, rotor_d, dom_dir
    )

    # Add turbine config to positions
    def add_config(positions):
        return [{**p, **turbine_config} for p in positions]

    grid_turbines = add_config(grid_pos)
    stag_turbines = add_config(stag_pos)

    # Calculate AEP with wake losses
    grid_aep = farm_aep_with_wake(grid_turbines, weibull_k, weibull_c, wind_rose)
    stag_aep = farm_aep_with_wake(stag_turbines, weibull_k, weibull_c, wind_rose)

    # Choose better layout
    best = 'staggered' if stag_aep['net_aep_mwh'] > grid_aep['net_aep_mwh'] else 'grid'

    return {
        'n_turbines':    n_rows * n_cols,
        'n_rows':        n_rows,
        'n_cols':        n_cols,
        'capacity_mw':   farm_capacity_mw(n_rows * n_cols, cap_kw),
        'spacing':       spacing,
        'dominant_wind': round(dom_dir, 1),
        'grid': {
            'turbines':      grid_pos,
            'aep':           grid_aep,
            'wake_loss_pct': grid_aep['wake_loss_pct'],
        },
        'staggered': {
            'turbines':      stag_pos,
            'aep':           stag_aep,
            'wake_loss_pct': stag_aep['wake_loss_pct'],
        },
        'recommended':   best,
        'best_net_aep':  stag_aep['net_aep_mwh'] if best == 'staggered' else grid_aep['net_aep_mwh'],
        'improvement_pct': round((stag_aep['net_aep_mwh'] - grid_aep['net_aep_mwh']) /
                                  max(grid_aep['net_aep_mwh'], 0.001) * 100, 2),
        'area_km2':      area_km2,
        'model':         'Jensen Wake + IEC 61400-1 Spacing',
    }