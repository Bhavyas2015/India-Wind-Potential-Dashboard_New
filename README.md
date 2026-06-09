# WindSite India v4 — Wind Energy Intelligence Platform

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://india-wind-potential-dashboardnew-sttisnarazbfogzwa7mxkn.streamlit.app/)

A production-grade geospatial wind energy site assessment platform for India, built with Python, FastAPI, and Streamlit.

---

## Live Demo

**Dashboard:** https://india-wind-potential-dashboardnew-sttisnarazbfogzwa7mxkn.streamlit.app/

---

## What It Does

WindSite India v4 answers three questions for wind energy development in India:

| Step | Question | Method |
|------|----------|--------|
| 1 | **WHERE** to put wind turbines? | Geospatial MCDA suitability mapping |
| 2 | **HOW MUCH** energy will they generate? | IEC 61400-1 physics + Weibull statistics |
| 3 | **WHY** is it financially viable? | INR financial model (LCOE / IRR / NPV) |

---

## Data Sources

| Data | Source | Resolution |
|------|--------|------------|
| Historical wind speed | NASA POWER MERRA-2 | 0.5° × 0.625° monthly |
| Real-time wind forecast | GFS via Open-Meteo | 0.25° hourly |
| ECMWF forecast | ECMWF IFS via Open-Meteo | 0.25° hourly |
| Land use / land cover | ESA WorldCover 2021 | 10m |
| Elevation + slope | SRTM 90m via OpenTopoData | 90m |
| Power line infrastructure | OpenStreetMap Overpass API | Real locations |
| Protected areas | MoEFCC + OSM | National database |

---

## Features

### Site Scouting (WHERE)
- Grid-based wind resource mapping across 6 Indian states
- AHP-MCDA suitability scoring with pairwise weight matrix
- AHP Consistency Ratio check (CR < 0.10 required)
- ESA WorldCover 10m land use classification
- SRTM elevation and slope analysis
- Real OSM power line distance (220kV / 400kV / 765kV)
- MoEFCC regulatory compliance check (airports, protected areas, CRZ)

### Wind Resource Analysis (HOW MUCH)
- Weibull distribution fitting (MLE Newton-Raphson)
- IEC 61400-1 Ed.3 power curve integration
- 16-sector wind rose from NASA WD10M data
- P50/P90 uncertainty analysis
- GFS + ECMWF real-time wind field animation
- 48-hour wind forecast per site

### Financial Model (WHY)
- CAPEX in Rs Crore/MW (MNRE 2024 parameters)
- LCOE in Rs/kWh
- IRR, NPV, payback period
- PPA revenue (state-wise rates)
- REC revenue (Rs 1500/MWh)
- Carbon credits (VER ~Rs 1250/tCO2)
- Homes powered calculation

### Advanced Features
- Jensen Top-Hat Wake Model (Katic et al. 1986)
- Grid + staggered farm layout optimizer
- PDF site assessment report (ReportLab)
- GeoJSON and CSV export
- Wind particle animation (GFS data)

---

## Covered States (AOIs)

| State | Region | Wind Potential |
|-------|--------|---------------|
| Gujarat | Kutch + Saurashtra plains | Very High |
| Rajasthan | Thar Desert corridor | Very High |
| Tamil Nadu | Coromandel coast | High |
| Maharashtra | Deccan plateau | Moderate-High |
| Andhra Pradesh | Eastern coast | High |
| Karnataka | Deccan + coastal | Moderate-High |

---

## Turbine Models

| Model | Capacity | Scale |
|-------|----------|-------|
| Micro 1kW | 1 kW | Small |
| Bergey Excel | 10 kW | Small |
| Enair E30 | 30 kW | Small |
| Enercon E33 | 330 kW | Utility |
| Suzlon S64 | 2.1 MW | Utility |
| Vestas V90 | 2.0 MW | Utility |
| Siemens SG5 | 5.0 MW | Utility |
| GE Haliade-X | 15.0 MW | Utility |

---

## Project Structure

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | HTML5, CSS3, JavaScript, Leaflet.js, Chart.js, Three.js |
| Backend API | FastAPI, Uvicorn |
| Web App | Streamlit 1.28+ |
| Physics | NumPy, SciPy |
| Geospatial | Rasterio, Shapely, GeoPandas |
| Data | httpx, diskcache |
| Reports | ReportLab |
| Hosting | Streamlit Cloud |

---

## India Wind Energy Context

| Parameter | Value | Source |
|-----------|-------|--------|
| Installed capacity (2024) | 46.9 GW | MNRE |
| Target by 2030 | 140 GW | MNRE |
| Technical potential | >300 GW | NIWE |
| RPO target (2030) | 24% | MoP |
| Avg LCOE (2024) | Rs 2.8–3.5/kWh | IRENA |
| Emission factor | 0.82 tCO₂/MWh | CEA 2024 |

---

## Future Enhancements

- [ ] 3D terrain visualization with wind flow overlay
- [ ] Mobile responsive design
- [ ] Higher resolution ECMWF ERA5 reanalysis integration
- [ ] Multi-scenario financial sensitivity analysis
- [ ] NIWE wind atlas integration
- [ ] State-wise RPO compliance tracking

---

## Disclaimer

This platform is developed for academic and planning purposes.
Wind data sourced from NASA POWER MERRA-2 reanalysis.
Financial projections based on MNRE/IRENA 2024 India parameters.
Site assessment results should be verified with on-site measurements before investment decisions.
Regulatory clearances must be obtained from MoEFCC and state nodal agencies.

---

## Author

Developed as part of a Geospatial Technology course project.