"""
WindSite India v4 - PDF Report Generator
Uses reportlab for professional site assessment reports.
"""
import io
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


def generate_pdf_report(
    analysis_result: Dict,
    selected_point: Optional[Dict] = None,
    output_path: Optional[str] = None
) -> bytes:
    """
    Generate a professional PDF wind site assessment report.

    Parameters:
        analysis_result: full analysis result from /api/analysis
        selected_point:  optional specific grid point to highlight
        output_path:     optional file path to save PDF

    Returns:
        PDF bytes
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable, PageBreak
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise ImportError("reportlab not installed. Run: pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=22,
        textColor=colors.HexColor('#00d084'),
        spaceAfter=6,
        fontName='Helvetica-Bold',
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#4a6278'),
        spaceAfter=20,
    )
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=colors.HexColor('#1a3a5c'),
        spaceBefore=16,
        spaceAfter=6,
        borderPad=4,
        fontName='Helvetica-Bold',
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=4,
        leading=14,
    )
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#7f8c8d'),
    )

    story = []
    summ = analysis_result.get('summary', {})
    state = analysis_result.get('state', 'India')
    aoi = analysis_result.get('aoi', 'gujarat').title()
    generated = analysis_result.get('generated', datetime.utcnow().isoformat())
    source_stats = analysis_result.get('source_stats', {})
    n_pts = analysis_result.get('n_points', 0)
    ahp_cr = analysis_result.get('ahp_cr', 0)
    ahp_ok = analysis_result.get('ahp_cr_ok', True)

    # Header
    story.append(Paragraph("WindSite India v4", title_style))
    story.append(Paragraph("Wind Energy Site Assessment Report", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#00d084')))
    story.append(Spacer(1, 0.4 * cm))

    # Report metadata table
    meta_data = [
        ['Report Generated', datetime.fromisoformat(generated).strftime('%d %B %Y, %H:%M UTC')],
        ['Region / State',   aoi + ' — ' + state],
        ['Data Source',      'NASA POWER MERRA-2 + ERA5 Reanalysis'],
        ['Land Use',         'ESA WorldCover 10m (2021)'],
        ['Elevation',        'SRTM 90m (OpenTopoData)'],
        ['MCDA Method',      'AHP Weighted Linear Combination'],
        ['Physics Standard', 'IEC 61400-1 Ed.3'],
        ['Financial Basis',  'MNRE/IRENA 2024 India Parameters'],
    ]
    meta_table = Table(meta_data, colWidths=[5 * cm, 12 * cm])
    meta_table.setStyle(TableStyle([
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('TEXTCOLOR',   (0, 0), (0, -1), colors.HexColor('#4a6278')),
        ('TEXTCOLOR',   (1, 0), (1, -1), colors.HexColor('#2c3e50')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white]),
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',     (0, 0), (-1, -1), 5),
        ('FONTNAME',    (0, 0), (0, -1), 'Helvetica-Bold'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.6 * cm))

    # Executive Summary
    story.append(Paragraph("1. Executive Summary", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dee2e6')))
    story.append(Spacer(1, 0.2 * cm))

    exec_data = [
        ['Metric', 'Value', 'Unit'],
        ['Total Grid Points Analysed', str(n_pts), 'points'],
        ['Valid Points (after exclusions)', str(summ.get('n_valid', 0)), 'points'],
        ['High Suitability Sites (>0.70)', str(summ.get('n_high', 0)), 'points'],
        ['High Suitability Area', str(summ.get('high_km2', 0)), 'km²'],
        ['High Sites as % of AOI', str(summ.get('pct_high', 0)), '%'],
        ['Mean Wind Speed at Hub', str(summ.get('mean_ws', 0)), 'm/s'],
        ['Mean Wind Power Density', str(summ.get('mean_wpd', 0)), 'W/m²'],
        ['Mean Capacity Factor', str(round((summ.get('mean_cf', 0) or 0) * 100, 1)), '%'],
        ['Mean Annual Energy Production', str(summ.get('mean_aep', 0)), 'MWh/turbine/yr'],
        ['Weibull Shape k', str(summ.get('wb_k', 0)), '-'],
        ['Weibull Scale c', str(summ.get('wb_c', 0)), 'm/s'],
        ['AHP Consistency Ratio', str(ahp_cr), 'CR < 0.10 = ' + ('Consistent' if ahp_ok else 'Revise')],
        ['NASA POWER Points', str(source_stats.get('nasa', 0)), 'points'],
        ['ERA5 Points', str(source_stats.get('era5', 0)), 'points'],
        ['Cache Hits', str(source_stats.get('cached', 0)), 'points'],
    ]

    exec_table = Table(exec_data, colWidths=[8 * cm, 4 * cm, 5 * cm])
    exec_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), colors.HexColor('#1a3a5c')),
        ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white]),
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',     (0, 0), (-1, -1), 5),
        ('ALIGN',       (1, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(exec_table)
    story.append(Spacer(1, 0.6 * cm))

    # Top sites
    story.append(Paragraph("2. Top 10 High-Suitability Sites", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dee2e6')))
    story.append(Spacer(1, 0.2 * cm))

    grid = analysis_result.get('grid', [])
    top_sites = sorted(
        [p for p in grid if p.get('mcda', {}).get('s', -1) >= 0],
        key=lambda p: p.get('mcda', {}).get('s', 0),
        reverse=True
    )[:10]

    if top_sites:
        site_data = [['#', 'Lat', 'Lon', 'WS m/s', 'WPD W/m²', 'CF%', 'AEP MWh', 'LULC', 'MCDA', 'IRR%']]
        for rank, pt in enumerate(top_sites, 1):
            mc = pt.get('mcda', {})
            fi = pt.get('finance', {})
            site_data.append([
                str(rank),
                str(pt.get('lat', '')),
                str(pt.get('lon', '')),
                str(pt.get('meanWS', '')),
                str(pt.get('wpd', '')),
                str(round((pt.get('cf', 0) or 0) * 100, 1)),
                str(pt.get('aep', '')),
                str(pt.get('lulc', '')),
                str(mc.get('s', '')),
                str(fi.get('irr_pct', '')),
            ])
        site_table = Table(site_data, colWidths=[0.6*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.8*cm, 1.2*cm, 1.8*cm, 2*cm, 1.4*cm, 1.4*cm])
        site_table.setStyle(TableStyle([
            ('BACKGROUND',  (0, 0), (-1, 0), colors.HexColor('#00d084')),
            ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
            ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0, 0), (-1, -1), 7.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0faf5'), colors.white]),
            ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('PADDING',     (0, 0), (-1, -1), 4),
            ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(site_table)
    else:
        story.append(Paragraph("No high-suitability sites found with current constraints.", body_style))

    story.append(Spacer(1, 0.6 * cm))

    # Selected site detail
    if selected_point:
        story.append(PageBreak())
        story.append(Paragraph("3. Selected Site Detailed Analysis", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dee2e6')))
        story.append(Spacer(1, 0.2 * cm))

        mc = selected_point.get('mcda', {})
        fi = selected_point.get('finance', {})
        wb = selected_point.get('wb', {})
        unc = selected_point.get('unc', {})

        detail_data = [
            ['LOCATION', '', 'WIND RESOURCE', ''],
            ['Latitude', str(selected_point.get('lat', '')),
             'Mean WS (hub)', str(selected_point.get('meanWS', '')) + ' m/s'],
            ['Longitude', str(selected_point.get('lon', '')),
             'Wind Power Density', str(selected_point.get('wpd', '')) + ' W/m²'],
            ['Elevation', str(selected_point.get('elev_m', '')) + ' m',
             'Weibull k', str(wb.get('k', ''))],
            ['Slope', str(selected_point.get('slope', '')) + '°',
             'Weibull c', str(wb.get('c', '')) + ' m/s'],
            ['Land Use', str(selected_point.get('lulc', '')),
             'Weibull R²', str(wb.get('r2', ''))],
            ['LULC Source', str(selected_point.get('lulc_src', '')),
             'IEC Class', str(selected_point.get('iec_cls', ''))],
            ['Grid Distance', str(selected_point.get('gridDist', '')) + ' km',
             'NREL Class', str(selected_point.get('nrel_cls', ''))],
            ['Data Source', str(selected_point.get('dataSource', '')),
             'Uncertainty ±', str(unc.get('aep_pct', '')) + '%'],
            ['MCDA SCORE', str(mc.get('s', '')),
             'MCDA Class', str(mc.get('cls', ''))],
            ['FINANCIAL', '', '', ''],
            ['CAPEX', 'Rs ' + str(fi.get('capex_cr', '')) + ' Cr',
             'LCOE', 'Rs ' + str(fi.get('lcoe_inr_kwh', '')) + '/kWh'],
            ['IRR', str(fi.get('irr_pct', '')) + '%',
             'Payback', str(fi.get('payback_yr', '')) + ' years'],
            ['NPV (25yr)', 'Rs ' + str(fi.get('npv_cr', '')) + ' Cr',
             'PLF', str(fi.get('plf_pct', '')) + '%'],
            ['AEP (P50)', str(fi.get('aep_mwh', '')) + ' MWh/yr',
             'Carbon', str(fi.get('carbon_tco2', '')) + ' tCO₂/yr'],
            ['Homes Powered', str(fi.get('homes_powered', '')),
             'Revenue/yr', 'Rs ' + str(fi.get('rev_tot_lakh', '')) + ' Lakh'],
        ]

        detail_table = Table(detail_data, colWidths=[4*cm, 5*cm, 4*cm, 5*cm])
        detail_table.setStyle(TableStyle([
            ('BACKGROUND',  (0, 0), (-1, 0), colors.HexColor('#1a3a5c')),
            ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
            ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND',  (0, 10), (-1, 10), colors.HexColor('#1a3a5c')),
            ('TEXTCOLOR',   (0, 10), (-1, 10), colors.white),
            ('FONTNAME',    (0, 10), (-1, 10), 'Helvetica-Bold'),
            ('FONTSIZE',    (0, 0), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, 9), [colors.HexColor('#f8f9fa'), colors.white]),
            ('ROWBACKGROUNDS', (0, 11), (-1, -1), [colors.HexColor('#f0faf5'), colors.white]),
            ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('PADDING',     (0, 0), (-1, -1), 5),
            ('FONTNAME',    (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME',    (2, 1), (2, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR',   (0, 1), (0, -1), colors.HexColor('#4a6278')),
            ('TEXTCOLOR',   (2, 1), (2, -1), colors.HexColor('#4a6278')),
        ]))
        story.append(detail_table)

    story.append(Spacer(1, 0.6 * cm))

    # India wind opportunity context
    story.append(Paragraph("4. India Wind Energy Context", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dee2e6')))
    story.append(Spacer(1, 0.2 * cm))

    context_data = [
        ['Parameter', 'Value', 'Source'],
        ['Installed Wind Capacity (2024)', '46.9 GW', 'MNRE'],
        ['Target by 2030', '140 GW', 'MNRE'],
        ['Capacity Gap', '93.1 GW', 'Calculated'],
        ['Technical Wind Potential', '>300 GW', 'NIWE'],
        ['RPO Target (2030)', '24%', 'MoP'],
        ['Average LCOE (India, 2024)', 'Rs 2.8-3.5/kWh', 'IRENA'],
        ['Nodal Agency', 'MNRE / SECI / NIWE', 'GoI'],
        ['Emission Factor (India Grid)', '0.82 tCO₂/MWh', 'CEA 2024'],
        ['REC Rate', 'Rs 1500/MWh', 'CERC'],
    ]
    ctx_table = Table(context_data, colWidths=[7*cm, 5*cm, 5*cm])
    ctx_table.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), colors.HexColor('#00d084')),
        ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0faf5'), colors.white]),
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('PADDING',     (0, 0), (-1, -1), 5),
    ]))
    story.append(ctx_table)
    story.append(Spacer(1, 0.4 * cm))

    # Disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dee2e6')))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Disclaimer: This report is generated by WindSite India v4 for academic and planning purposes. "
        "Wind data sourced from NASA POWER MERRA-2 reanalysis. Financial projections based on MNRE/IRENA "
        "2024 India parameters. Site assessment results should be verified with on-site measurements "
        "before investment decisions. Regulatory clearances must be obtained from MoEFCC and state nodal agencies.",
        label_style
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()

    if output_path:
        Path(output_path).write_bytes(pdf_bytes)

    return pdf_bytes