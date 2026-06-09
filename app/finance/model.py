import math

PPA_RATES = {
    'Gujarat': 3.50, 'Rajasthan': 3.20, 'Tamil Nadu': 3.80,
    'Maharashtra': 3.60, 'Andhra': 3.40, 'Karnataka': 3.55, 'default': 3.50
}
INR_USD = 83.5
REC_RATE = 1500
CARBON_USD_TCO2 = 15.0
EF_TCO2_MWH = 0.82
PLF_DERATE = 0.95
INDIA_AVG_KWH_HOME = 1200

def _crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)

def compute_finance(cf, cap_kw, tkey, state='default', turbines=None,
                    ppa_override=None, dr=0.10, lt=25, capex_cr_override=None,
                    include_rec=True, include_carbon=True):
    if cf < 0.01 or cap_kw <= 0:
        return {}
    t = turbines.get(tkey, {}) if turbines else {}
    capex_cr_mw = capex_cr_override or t.get('capex_cr_mw', 5.5)
    cap_mw = cap_kw / 1000.0
    aep_mwh = cf * cap_kw * 8760 / 1000 * PLF_DERATE
    aep_kwh = aep_mwh * 1000
    capex_tot = capex_cr_mw * cap_mw * 1e7
    opex_yr = 0.35 * cap_mw * 1e7
    ppa = ppa_override or PPA_RATES.get(state, PPA_RATES['default'])
    rev_ppa = aep_kwh * ppa
    rev_rec = aep_mwh * REC_RATE if include_rec else 0
    rev_cc = aep_mwh * EF_TCO2_MWH * CARBON_USD_TCO2 * INR_USD if include_carbon else 0
    rev_tot = rev_ppa + rev_rec + rev_cc
    net_yr = rev_tot - opex_yr
    crf = _crf(dr, lt)
    lcoe_num = capex_tot * crf + opex_yr
    lcoe_kwh = round(lcoe_num / aep_kwh, 2) if aep_kwh > 0 else None
    npv = -capex_tot + sum(net_yr / (1 + dr) ** i for i in range(1, lt + 1))
    lo, hi = -0.5, 3.0
    irr_val = 0.1
    for _ in range(100):
        mid = (lo + hi) / 2
        v = -capex_tot + sum(net_yr / (1 + mid) ** i for i in range(1, lt + 1))
        if abs(v) < 100:
            irr_val = mid
            break
        if v > 0:
            lo = mid
        else:
            hi = mid
        irr_val = mid
    pb = round(capex_tot / net_yr, 1) if net_yr > 0 else None
    homes = int(aep_mwh * 1000 / INDIA_AVG_KWH_HOME)
    co2_yr = round(aep_mwh * EF_TCO2_MWH, 1)
    return {
        'capex_cr': round(capex_cr_mw * cap_mw, 3),
        'lcoe_inr_kwh': lcoe_kwh,
        'npv_cr': round(npv / 1e7, 3),
        'irr_pct': round(irr_val * 100, 2),
        'payback_yr': pb,
        'aep_mwh': round(aep_mwh, 2),
        'plf_pct': round(cf * PLF_DERATE * 100, 2),
        'rev_ppa_lakh': round(rev_ppa / 1e5, 2),
        'rev_rec_lakh': round(rev_rec / 1e5, 2),
        'rev_cc_lakh': round(rev_cc / 1e5, 2),
        'rev_tot_lakh': round(rev_tot / 1e5, 2),
        'carbon_tco2': co2_yr,
        'homes_powered': homes,
        'state': state,
        'cap_kw': cap_kw,
        'ppa_rate': ppa,
    }