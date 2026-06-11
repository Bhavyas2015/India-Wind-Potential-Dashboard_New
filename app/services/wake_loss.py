import numpy as np
import math
from typing import List, Dict, Tuple, Optional


# Jensen Top-Hat Wake Model
# Reference: Jensen (1983), Katic et al. (1986)

def jensen_wake_deficit(
    distance_m: float,
    rotor_diameter_m: float,
    thrust_coefficient: float = 0.8,
    wake_decay_k: float = 0.04
) -> float:
    """
    Jensen top-hat wake model deficit at a given downstream distance.

    Parameters:
        distance_m:          downstream distance in metres
        rotor_diameter_m:    rotor diameter in metres
        thrust_coefficient:  Ct (default 0.8 for typical onshore turbine)
        wake_decay_k:        wake decay constant (0.04 offshore, 0.075 onshore)

    Returns:
        velocity deficit (0 to 1) — multiply by free-stream wind speed
    """
    if distance_m <= 0:
        return 0.0

    r0 = rotor_diameter_m / 2.0
    r_wake = r0 + wake_decay_k * distance_m

    deficit = (1.0 - math.sqrt(1.0 - thrust_coefficient)) * (r0 / r_wake) ** 2
    return float(np.clip(deficit, 0.0, 1.0))


def wake_affected_speed(
    free_stream_ms: float,
    turbines: List[Dict],
    target_idx: int,
    wind_direction_deg: float,
    wake_decay_k: float = 0.075
) -> float:
    """
    Calculate wind speed at a target turbine accounting for upstream wakes.

    Parameters:
        free_stream_ms:    free-stream wind speed in m/s
        turbines:          list of dicts with keys: lat, lon, rotor_d, ct
        target_idx:        index of target turbine
        wind_direction_deg: wind direction in degrees
        wake_decay_k:      wake decay constant

    Returns:
        effective wind speed at target turbine in m/s
    """
    if not turbines or target_idx >= len(turbines):
        return free_stream_ms

    target = turbines[target_idx]
    wd_rad = math.radians(wind_direction_deg)

    total_deficit_sq = 0.0

    for i, upstream in enumerate(turbines):
        if i == target_idx:
            continue

        dx = (target['lon'] - upstream['lon']) * 111000 * math.cos(math.radians(upstream['lat']))
        dy = (target['lat'] - upstream['lat']) * 111000

        downstream_dist = dx * math.sin(wd_rad) + dy * math.cos(wd_rad)
        if downstream_dist <= 0:
            continue

        lateral_dist = abs(-dx * math.cos(wd_rad) + dy * math.sin(wd_rad))
        rotor_r = upstream.get('rotor_d', 90) / 2.0
        wake_r = rotor_r + wake_decay_k * downstream_dist

        if lateral_dist > wake_r:
            continue

        partial = lateral_dist / wake_r if wake_r > 0 else 0
        overlap = max(0.0, 1.0 - partial)

        ct = upstream.get('ct', 0.8)
        deficit = (1.0 - math.sqrt(1.0 - ct)) * (rotor_r / wake_r) ** 2
        total_deficit_sq += (deficit * overlap) ** 2

    total_deficit = math.sqrt(total_deficit_sq)
    return float(max(0.1, free_stream_ms * (1.0 - total_deficit)))


def farm_aep_with_wake(
    turbines: List[Dict],
    weibull_k: float,
    weibull_c: float,
    wind_rose: Optional[Dict] = None,
    wake_decay_k: float = 0.075,
    dv: float = 0.5
) -> Dict:
    """
    Calculate farm-level AEP with wake losses using Jensen model.

    Parameters:
        turbines:     list of turbine dicts (lat, lon, rotor_d, ct, capKW, power_curve)
        weibull_k:    Weibull shape parameter
        weibull_c:    Weibull scale parameter m/s
        wind_rose:    optional wind rose dict for directional weighting
        wake_decay_k: wake decay constant
        dv:           wind speed bin size

    Returns:
        dict with gross_aep, net_aep, wake_loss_pct per turbine and total
    """
    from scipy.special import gamma as gf

    n = len(turbines)
    if n == 0:
        return {'gross_aep_mwh': 0, 'net_aep_mwh': 0, 'wake_loss_pct': 0, 'n_turbines': 0}

    # Wind directions to consider
    if wind_rose and wind_rose.get('sectors'):
        directions = [(s['center_deg'], s['frequency']) for s in wind_rose['sectors'] if s['frequency'] > 0.001]
    else:
        directions = [(d, 1.0 / 16) for d in range(0, 360, 22)]

    v_arr = np.arange(0, 35 + dv, dv)

    def weibull_pdf(v):
        out = np.zeros_like(v)
        m = v > 0
        vc = v[m] / weibull_c
        out[m] = (weibull_k / weibull_c) * (vc ** (weibull_k - 1)) * np.exp(-(vc ** weibull_k))
        return out

    pdf = weibull_pdf(v_arr)

    turbine_gross = []
    turbine_net = []

    for i, t in enumerate(turbines):
        cap = t.get('capKW', 2000)
        ci = t.get('ci', 3.5)
        co = t.get('co', 25.0)
        curve = t.get('curve', [])

        def power_at_v(v):
            if v < ci or v >= co or not curve:
                return 0.0
            idx = min(int(v), len(curve) - 2)
            f = v - idx
            return curve[idx] * (1 - f) + curve[min(idx + 1, len(curve) - 1)] * f

        gross_cf = float(np.clip(np.trapezoid([power_at_v(v) for v in v_arr] * pdf, v_arr) / max(cap, 1), 0, 0.65))
        gross_aep = gross_cf * cap * 8760 / 1000
        turbine_gross.append(gross_aep)

        net_aep_dir = 0.0
        for wd_deg, freq in directions:
            dir_net = 0.0
            for v in v_arr[v_arr > 0]:
                v_eff = wake_affected_speed(float(v), turbines, i, wd_deg, wake_decay_k)
                p = power_at_v(v_eff)
                pdf_v = weibull_pdf(np.array([v]))[0]
                dir_net += p * pdf_v * dv * freq
            net_aep_dir += dir_net

        net_aep = float(np.clip(net_aep_dir * cap * 8760 / 1000, 0, gross_aep))
        turbine_net.append(net_aep)

    total_gross = sum(turbine_gross)
    total_net = sum(turbine_net)
    wake_loss_pct = round((1 - total_net / max(total_gross, 0.001)) * 100, 2)

    return {
        'gross_aep_mwh':    round(total_gross, 2),
        'net_aep_mwh':      round(total_net, 2),
        'wake_loss_pct':    wake_loss_pct,
        'n_turbines':       n,
        'per_turbine': [
            {
                'idx':          i,
                'gross_mwh':    round(turbine_gross[i], 2),
                'net_mwh':      round(turbine_net[i], 2),
                'wake_loss_pct': round((1 - turbine_net[i] / max(turbine_gross[i], 0.001)) * 100, 2)
            }
            for i in range(n)
        ],
        'model': 'Jensen Top-Hat Wake Model (Katic et al. 1986)',
    }