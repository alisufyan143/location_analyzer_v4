import asyncio
import calendar
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from location_analyzer.api.schemas import PredictRequest, PredictResponse, TimeSeriesPrediction, GranularTimeSeries, PlotExportRequest
from location_analyzer.pipeline.inference_pipeline import InferencePipeline
from location_analyzer.data.repository import PostcodeRepository

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_session_factory(request: Request):
    return getattr(request.app.state, "session_factory", None)


# ── Route-level phase logging ─────────────────────────────────────────────

def _log_phase(phase: str, name: str, detail: str) -> None:
    logger.info("\n  [PHASE %s] %s\n  %s", phase, name, detail)


@router.post("/predict", response_model=PredictResponse)
async def predict_sales(request_body: PredictRequest, request: Request):
    """
    Predict sales: use DB if we have features for this postcode, else scrape then persist.
    Never holds a DB connection during scraping or model inference (no bottleneck).
    """
    model_service = request.app.state.model_service
    if not model_service:
        raise HTTPException(status_code=500, detail="PredictionService is offline.")

    postcode = request_body.postcode.upper().strip()

    logger.info(
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║  /predict  REQUEST RECEIVED                              ║\n"
        "╚══════════════════════════════════════════════════════════╝\n"
        "  INPUT  postcode=%s  branch=%s",
        postcode, request_body.branch_name or "(none)",
    )

    session_factory = _get_session_factory(request)
    features        = None
    display_data    = {}

    # ── Phase R1: DB Cache Lookup ─────────────────────────────────────────────
    source_type = "live_scrape"
    
    _log_phase("R1", "DB Cache Lookup", f"postcode={postcode}")
    if session_factory and not request_body.force_refresh:
        with session_factory() as session:
            repo     = PostcodeRepository(session)
            features = repo.get_features_for_postcode(postcode)

    if features is not None:
        # DB hit — load rich display data
        _log_phase("R1b", "Load Display Data from DB", f"postcode={postcode}")
        if session_factory:
            with session_factory() as session:
                repo = PostcodeRepository(session)
                display_data = repo.get_display_data(postcode)
        source_type = "database_cache"
        logger.info("  [PHASE R1] DB HIT -- skipping live scrape")
    else:
        # DB miss — run scrapers
        _log_phase("R2", "Live Scraping Pipeline", f"postcode={postcode}")
        pipeline = InferencePipeline()
        features = await asyncio.to_thread(pipeline.run, postcode)
        if not features:
            raise HTTPException(status_code=404, detail=f"Could not extract any data for postcode: {postcode}")

        # Extract rich display data before persists
        display_data = features.pop("_display", {})

        # ── Phase R3: Persist to DB ───────────────────────────────────────────
        _log_phase("R3", "Persist to DB", f"postcode={postcode}")
        
        # Dual-validation check: Don't poison the DB cache if scrapers failed or choked
        demographics_valid = features.get("population", 0) > 0 and features.get("de") is not None
        crystalroof_valid = "transport" in display_data and isinstance(display_data["transport"], dict)
        
        if demographics_valid and crystalroof_valid:
            if session_factory:
                with session_factory() as session:
                    repo = PostcodeRepository(session)
                    repo.save_scraped_result(postcode, features, display_data=display_data)
                    session.commit()
                logger.info("  [PHASE R3] DB write complete")
        else:
            logger.warning("  [PHASE R3] Scrape returned partial or missing critical data. Bypassing Cache/DB.")

    if request_body.branch_name:
        features["Branch Name"] = request_body.branch_name

    # ── Phase R5: ML Inference (12-month time series) ─────────────────────────
    _log_phase("R5", "ML Model Inference", f"features_count={len(features)}")

    import pandas as pd
    from datetime import timedelta
    import calendar

    now = datetime.now()
    # Daily sequence: Today until end of Month 12
    # End date is start of Month 13 - 1 day
    end_month_date = now + pd.DateOffset(months=12)
    last_day_of_12th = datetime(end_month_date.year, end_month_date.month, 1) + pd.DateOffset(months=1) - timedelta(days=1)
    
    # 1. Generate all dates for the year
    daily_dates = []
    curr = now
    while curr <= last_day_of_12th:
        daily_dates.append(curr)
        curr += timedelta(days=1)
        
    # 2. Prepare features for every single day
    pred_features = []
    for d in daily_dates:
        pred_features.append({**features.copy(), "Date": d.strftime("%Y-%m-%d")})
        
    # 3. Batch predict all ~365 days
    raw_preds = model_service.predict(pred_features)
    
    # 4. Build daily sequence
    daily_ts = []
    daily_pred_map = {}
    for d, p in zip(daily_dates, raw_preds):
        date_str = d.strftime("%Y-%m-%d")
        daily_ts.append(TimeSeriesPrediction(
            date=date_str, 
            predicted_sales=round(p, 2)
        ))
        daily_pred_map[date_str] = p

    # 5. Build weekly sequence: Monday-based weeks starting from the week of 'now'
    weekly_ts = []
    curr_week_start = now - timedelta(days=now.weekday())
    while curr_week_start <= last_day_of_12th:
        week_sum = 0
        for i in range(7):
            day = curr_week_start + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            # If the day falls outside our prediction window (e.g. earlier days in the first week),
            # we use the first predicted day's rate as a fallback.
            rate = daily_pred_map.get(day_str, raw_preds[0])
            week_sum += rate
        
        # Label as 'Week of {Date}'
        weekly_ts.append(TimeSeriesPrediction(
            date=curr_week_start.strftime("%Y-%m-%d"),
            predicted_sales=round(week_sum, 2)
        ))
        curr_week_start += timedelta(days=7)

    # 6. Build monthly sequence: Current month + 11
    monthly_ts = []
    for i in range(12):
        target_date = now + pd.DateOffset(months=i)
        y, m = target_date.year, target_date.month
        
        # Sum all daily predictions that fall within this year/month
        month_sum = sum(
            p for d, p in zip(daily_dates, raw_preds) 
            if d.year == y and d.month == m
        )
        
        # If today is halfway through the current month, we won't have the full month's predictions.
        # So we scale it up to a full month for an accurate forecast representation.
        _, days_in_month = calendar.monthrange(y, m)
        days_predicted = sum(1 for d in daily_dates if d.year == y and d.month == m)
        if days_predicted > 0:
            avg_daily_for_month = month_sum / days_predicted
            month_total = avg_daily_for_month * days_in_month
        else:
            month_total = 0
            
        monthly_ts.append(TimeSeriesPrediction(
            date=target_date.strftime("%b %Y"),
            predicted_sales=round(month_total, 2)
        ))
    
    time_series = GranularTimeSeries(daily=daily_ts, weekly=weekly_ts, monthly=monthly_ts)

    logger.info(
        "  [PHASE R5] Inference complete -- 12 months predicted (Monthly/Weekly/Daily generated)\n"
        "  MONTHLY PREDICTIONS:\n%s",
        "\n".join(f"    {ts.date}: £{ts.predicted_sales:>10,.2f}" for ts in monthly_ts),
    )

    # ── Phase R6: Persist Prediction to DB ───────────────────────────────────
    if session_factory and monthly_ts:
        _log_phase("R6", "Persist Prediction to DB", f"postcode={postcode}")
        median_pred = monthly_ts[0].predicted_sales
        preds = [t.predicted_sales for t in monthly_ts]
        with session_factory() as session:
            repo = PostcodeRepository(session)
            repo.upsert_postcode(
                postcode,
                prediction=median_pred,
                min_prediction=min(preds) if preds else None,
                max_prediction=max(preds) if preds else None,
            )
            session.commit()
        logger.info(
            "  [PHASE R6] Prediction stored: first_month=£%.2f  min=£%.2f  max=£%.2f",
            median_pred, min(preds), max(preds),
        )

    # ── Final response ────────────────────────────────────────────────────────
    logger.info(
        "\n"
        "╔══════════════════════════════════════════════════════════╗\n"
        "║  /predict  RESPONSE SENT                                 ║\n"
        "╚══════════════════════════════════════════════════════════╝\n"
        "  postcode=%s  predicted_sales=£%.2f (Month 1)\n",
        postcode,
        monthly_ts[0].predicted_sales,
    )

    return PredictResponse(
        postcode=postcode,
        source=source_type,
        predicted_sales=monthly_ts[0].predicted_sales,
        features=features,
        display_data=display_data,
        time_series=time_series,
    )
@router.post("/export-plot", response_class=HTMLResponse)
async def export_bokeh_plot(request_body: PlotExportRequest):
    """
    Generate an interactive Bokeh plot of the forecast and return it as a standalone HTML document.
    """
    try:
        from bokeh.plotting import figure
        from bokeh.embed import file_html
        from bokeh.resources import CDN
        from bokeh.models import NumeralTickFormatter, HoverTool, ColumnDataSource, LabelSet, Div
        from bokeh.layouts import column
    except ImportError:
        raise HTTPException(status_code=500, detail="Bokeh library is not installed.")

    postcode = request_body.postcode.upper()
    dates = request_body.dates
    sales = request_body.sales
    granularity = request_body.granularity.capitalize()

    title = f"{granularity} Sales Forecast for {postcode}"

    # Format values for labels
    formatted_sales = [f"£{v:,.0f}" for v in sales]
    source = ColumnDataSource(data=dict(x=dates, y=sales, text=formatted_sales))

    # Make the plot wider for weekly/daily data
    plot_width = max(1200, len(dates) * 40)

    p = figure(
        title=title,
        x_range=dates,
        height=500,
        width=plot_width,
        tools="pan,box_zoom,reset,save",
        toolbar_location="right"
    )

    # Plot as vertical area/bar or line
    p.vbar(x='x', top='y', width=0.9, color="#10b981", alpha=0.8, source=source)
    p.line(x='x', y='y', color="#047857", line_width=2, source=source)
    p.circle(x='x', y='y', color="#047857", size=6, source=source)

    # Add data labels
    labels = LabelSet(
        x='x', y='y', text='text', source=source,
        text_align='center', text_baseline='bottom',
        text_font_size="9pt", text_color="#1f2937", y_offset=5
    )
    p.add_layout(labels)

    p.yaxis.formatter = NumeralTickFormatter(format="£0,0")
    p.xaxis.major_label_orientation = 1.0

    hover = HoverTool()
    hover.tooltips = [
        ("Date", "@x"),
        ("Predicted Sales", "£@y{0,0.00}")
    ]
    p.add_tools(hover)

    p.xgrid.grid_line_color = None

    # Build Demographics HTML display
    features = request_body.features
    dd = request_body.display_data

    html_parts = []
    
    html_parts.append(f"<h2 style='font-family: sans-serif; color: #111827;'>Location Insights: {postcode}</h2>")
    
    # Core Demographics
    html_parts.append("<div style='display: flex; gap: 2rem; font-family: sans-serif;'>")
    
    html_parts.append("<div style='flex: 1;'>")
    html_parts.append("<h3 style='color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;'>Core Demographics</h3>")
    html_parts.append("<table style='width: 100%; border-collapse: collapse; font-size: 14px;'>")
    def add_row(k, v):
        html_parts.append(f"<tr style='border-bottom: 1px solid #f3f4f6;'><td style='padding: 8px 0; color: #6b7280; font-weight: 500;'>{k}</td><td style='padding: 8px 0; text-align: right; color: #111827;'>{v}</td></tr>")
    
    add_row("Population", f"{features.get('population', 0):,}")
    add_row("Households", f"{features.get('households', 0):,}")
    add_row("Non-White Population", f"{features.get('non-white', 0)}%")
    add_row("Avg Household Income", f"£{features.get('avg_household_income', 0):,}")
    add_row("Unemployment Rate", f"{features.get('unemployment_rate', 0)}%")
    html_parts.append("</table></div>")
    # Helper to parse list of dicts (like those in ethnicity/religion/occupations)
    def render_list_of_dicts(title, data_list):
        if not data_list or not isinstance(data_list, list):
            return ""
        html = f"<div style='flex: 1;'><h3 style='color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;'>{title}</h3>"
        html += "<table style='width: 100%; border-collapse: collapse; font-size: 14px;'>"
        for item in data_list:
            name = item.get('name', '')
            pct = item.get('pct', '')
            if pct != '':
                pct = f"{pct}%"
            html += f"<tr style='border-bottom: 1px solid #f3f4f6;'><td style='padding: 8px 0; color: #6b7280; font-weight: 500;'>{name}</td><td style='padding: 8px 0; text-align: right; color: #111827;'>{pct}</td></tr>"
        html += "</table></div>"
        return html

    # Ethnicity, Religion, Age, Household are nested under display_data['ethnicity']['sections']
    ethnicity_data = dd.get('ethnicity', {})
    sections = ethnicity_data.get('sections', {})
    
    if 'Ethnicity' in sections:
        html_parts.append(render_list_of_dicts("Ethnicity Breakdown", sections['Ethnicity']))
    if 'Religion' in sections:
        html_parts.append(render_list_of_dicts("Religion", sections['Religion']))
        
    html_parts.append("</div>") # End top flex container

    # Second row of demographics
    html_parts.append("<div style='display: flex; gap: 2rem; font-family: sans-serif; margin-top: 2rem;'>")
    if 'Age' in sections:
        html_parts.append(render_list_of_dicts("Age Profile", sections['Age']))
    if 'Household' in sections:
        html_parts.append(render_list_of_dicts("Household Types", sections['Household']))

    # Occupations from display_data['occupation']
    if 'occupation' in dd and isinstance(dd['occupation'], dict):
        html = f"<div style='flex: 1;'><h3 style='color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;'>Occupations & Education</h3>"
        html += "<table style='width: 100%; border-collapse: collapse; font-size: 14px;'>"
        for k, v in dd['occupation'].items():
            if k == 'students':
                html += f"<tr style='border-bottom: 1px solid #f3f4f6;'><td style='padding: 8px 0; color: #6b7280; font-weight: 500;'>Full-time Students</td><td style='padding: 8px 0; text-align: right; color: #111827;'>{v}</td></tr>"
            else:
                formatted_k = k.replace('_', ' ').title()
                html += f"<tr style='border-bottom: 1px solid #f3f4f6;'><td style='padding: 8px 0; color: #6b7280; font-weight: 500;'>{formatted_k}</td><td style='padding: 8px 0; text-align: right; color: #111827;'>{v}%</td></tr>"
        html += "</table></div>"
        html_parts.append(html)

    html_parts.append("</div>") # End middle flex container
    
    # Amenities / Transport
    html_parts.append("<div style='display: flex; gap: 2rem; font-family: sans-serif; margin-top: 2rem;'>")
    
    # Transport Stations
    if 'transport' in dd and 'stations' in dd['transport'] and isinstance(dd['transport']['stations'], list):
        stations = dd['transport']['stations']
        html = f"<div style='flex: 1;'><h3 style='color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;'>Transport Stations</h3>"
        for item in stations[:5]:
            name = item.get('name', 'Unknown')
            dist = item.get('distance', '')
            stype = item.get('type', '')
            html += f"<div style='margin-bottom: 8px;'><span style='background: #e0e7ff; padding: 4px 8px; border-radius: 4px; font-size: 13px; color: #3730a3; display: inline-block;'>{name} <b>{dist} mi</b> ({stype})</span></div>"
        html += "</div>"
        html_parts.append(html)

    # Restaurants and Pubs
    if 'amenities' in dd and isinstance(dd['amenities'], dict) and dd['amenities']:
        html = f"<div style='flex: 1;'><h3 style='color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;'>Nearby Amenities</h3>"
        amenities_html = ""
        for k, items in dd['amenities'].items():
            if isinstance(items, list):
                count = len(items)
                title = f"{k.capitalize()} ({count})"
                amenities_html += f"<div style='margin-bottom: 1rem;'><strong style='color: #374151; font-size: 14px;'>{title}</strong><br/>"
                for item in items[:5]: # Show top 5
                    name = item.get('name', 'Unknown')
                    dist = item.get('distance', '')
                    amenities_html += f"<span style='background: #f3f4f6; padding: 4px 8px; border-radius: 4px; font-size: 13px; color: #4b5563; margin-right: 8px; margin-bottom: 8px; margin-top: 4px; display: inline-block;'>{name} <b>{dist}</b></span>"
                if count > 5:
                    amenities_html += f"<span style='font-size: 13px; color: #6b7280;'>+{count - 5} more...</span>"
                amenities_html += "</div>"
        html += amenities_html + "</div>"
        html_parts.append(html)
        
    html_parts.append("</div>") # End bottom flex container

    info_div = Div(text="".join(html_parts), width=1000, margin=(20, 0, 40, 0))

    layout = column(p, info_div)

    html = file_html(layout, CDN, title)
    return HTMLResponse(content=html)
