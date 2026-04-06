import asyncio
import calendar
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from location_analyzer.api.schemas import PredictRequest, PredictResponse, TimeSeriesPrediction, GranularTimeSeries, PlotExportRequest
from location_analyzer.pipeline.inference_pipeline import InferencePipeline
from location_analyzer.data.repository import PostcodeRepository
from location_analyzer.data.models import BranchMaturity
from location_analyzer.utils.calendar_utils import CalendarUtility
from location_analyzer.utils.brand_matcher import BrandMatcher

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
        "  INPUT  postcode=%s  branch=%s  range=%s/%s to %s/%s",
        postcode, request_body.branch_name or "(none)",
        request_body.from_month, request_body.from_year,
        request_body.to_month, request_body.to_year
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

    # ── Phase R5: ML Inference (user-defined date range) ──────────────────────
    _log_phase("R5", "V3 ML Model Inference", f"features_count={len(features)}")

    import pandas as pd
    from datetime import timedelta
    import calendar

    now = datetime.now()

    # ── Resolve date range from request or use sensible defaults ──────────────
    # ── Resolve date range from request or use sensible defaults ──────────────
    from_month = request_body.from_month or now.month
    from_year  = request_body.from_year  or now.year
    
    # Smart Default Target:
    # If from_year is in the past (historical backtesting), default to 12 months from THAT start.
    # Otherwise, default to 12 months from NOW.
    if request_body.from_year and request_body.from_year < now.year:
        _base_start = datetime(from_year, from_month, 1)
        _default_end = _base_start + pd.DateOffset(months=12)
    else:
        _default_end = now + pd.DateOffset(months=12)

    to_month = request_body.to_month or _default_end.month
    to_year  = request_body.to_year  or _default_end.year

    # Build start (1st of from_month) and end (last day of to_month)
    range_start = datetime(from_year, from_month, 1)
    range_end   = datetime(to_year, to_month, 1) + pd.DateOffset(months=1) - timedelta(days=1)

    # Validate: end must be after start
    if range_end < range_start:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="'To' date must be after 'From' date.")

    _log_phase("R5a", "Date Range Resolved",
               f"from={from_year}-{from_month:02d} to={to_year}-{to_month:02d} "
               f"({int((range_end - range_start).days)} days)")

    # 1. Generate all daily dates across the range
    daily_dates = []
    curr = range_start
    while curr <= range_end:
        daily_dates.append(curr)
        curr += timedelta(days=1)

    # 2. Determine Brand String and situational flags
    inferred_brand = request_body.inferred_brand_override
    if not inferred_brand:
        inferred_brand = BrandMatcher.get_brand_id(request_body.branch_name)
    
    situational = {
        "is_logistics_strike": int(request_body.is_logistics_strike),
        "is_delivery_crackdown": int(request_body.is_delivery_crackdown)
    }

    # --- FETCH DYNAMIC MATURITY FROM DB ---
    # Default is the incoming request (or 1000 standard).
    base_days_since_open = request_body.days_since_open if request_body.days_since_open is not None else 1000
    anchor_date = None
    
    if session_factory and request_body.branch_name:
        with session_factory() as session:
            b_name_strip = request_body.branch_name.strip()
            maturity_record = session.query(BranchMaturity).filter_by(
                branch_name=b_name_strip, 
                postcode=postcode
            ).first()
            if maturity_record:
                base_days_since_open = maturity_record.base_days_since_open
                anchor_date = maturity_record.last_known_date
                logger.info("  [MATURITY] DB Anchor Hit: %d days as of %s", base_days_since_open, anchor_date.strftime('%Y-%m-%d'))
            else:
                logger.info("  [MATURITY] DB Anchor Miss: Defaulting base to %d days", base_days_since_open)

    # 3. Prepare unique high-fidelity feature dicts for every single day
    pred_features = []
    for d in daily_dates:
        f_day = features.copy()
        
        # Inject Temporal Flags from CalendarUtility
        temporal_flags = CalendarUtility.get_features_for_date(d, situational)
        f_day.update(temporal_flags)
        
        # --- ROLLING TIME-SERIES MATURITY ---
        if anchor_date:
            delta_days = (d - anchor_date).days
            rolling_maturity = max(0, base_days_since_open + delta_days)
        else:
            delta_days = (d - range_start).days
            rolling_maturity = max(0, base_days_since_open + delta_days)

        # Inject Contextual Metadata
        f_day["Inferred_Brand"] = inferred_brand
        f_day["Days_Since_Open"] = rolling_maturity
        
        pred_features.append(f_day)

    # 4. Batch predict all days using the V4 Ensemble
    raw_preds = model_service.predict(pred_features)

    # 3.5 Apply weekly sales inflation if toggled on
    if request_body.inflate_sales and request_body.inflate_amount:
        WEEKLY_INFLATION = float(request_body.inflate_amount)
        DAILY_INFLATION = WEEKLY_INFLATION / 7.0
        raw_preds = [p + DAILY_INFLATION for p in raw_preds]
        logger.info("  [PHASE R5] Sales inflation ACTIVE: +£%.2f/day (£%.0f/week)", DAILY_INFLATION, WEEKLY_INFLATION)

    # 4. Build daily time series
    daily_ts = []
    daily_pred_map = {}
    for d, p in zip(daily_dates, raw_preds):
        date_str = d.strftime("%Y-%m-%d")
        daily_ts.append(TimeSeriesPrediction(date=date_str, predicted_sales=round(p, 2)))
        daily_pred_map[date_str] = p

    # 5. Build weekly sequence: Monday-based weeks within range
    weekly_ts = []
    # Start from the Monday of the week that contains range_start
    curr_week_start = range_start - timedelta(days=range_start.weekday())
    while curr_week_start <= range_end:
        week_sum = 0
        for i in range(7):
            day     = curr_week_start + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            # Use nearest available prediction if day falls outside range
            rate = daily_pred_map.get(day_str, raw_preds[0] if raw_preds else 0)
            week_sum += rate
        weekly_ts.append(TimeSeriesPrediction(
            date=curr_week_start.strftime("%Y-%m-%d"),
            predicted_sales=round(week_sum, 2)
        ))
        curr_week_start += timedelta(days=7)

    # 6. Build monthly sequence: one entry per calendar month in the range
    monthly_ts = []
    month_cursor = datetime(from_year, from_month, 1)
    end_of_range = datetime(to_year, to_month, 1)
    while month_cursor <= end_of_range:
        y, m = month_cursor.year, month_cursor.month
        # Sum all daily predictions that fall in this year-month
        month_sum = sum(
            p for d, p in zip(daily_dates, raw_preds)
            if d.year == y and d.month == m
        )
        _, days_in_month  = calendar.monthrange(y, m)
        days_predicted    = sum(1 for d in daily_dates if d.year == y and d.month == m)
        if days_predicted > 0:
            # Scale to full calendar month for apples-to-apples comparison
            month_total = (month_sum / days_predicted) * days_in_month
        else:
            month_total = 0
        monthly_ts.append(TimeSeriesPrediction(
            date=month_cursor.strftime("%b %Y"),
            predicted_sales=round(month_total, 2)
        ))
        month_cursor = (month_cursor + pd.DateOffset(months=1)).to_pydatetime()

    time_series = GranularTimeSeries(daily=daily_ts, weekly=weekly_ts, monthly=monthly_ts)


    logger.info(
        "  [PHASE R5] Inference complete -- 12 months predicted (Monthly/Weekly/Daily generated)\n"
        "  MONTHLY PREDICTIONS:\n%s",
        "\n".join(f"    {ts.date}: £{ts.predicted_sales:>10,.2f}" for ts in monthly_ts),
    )

    # ── Phase R6: Stripped (Prediction Caching removed) ─────────────────────
    # We no longer cache static predictions into SQLite. It caused stale data 
    # bugs. High-speed RAM inference executes in ~45ms dynamically every click.
    
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
    Generate a comprehensive interactive Bokeh report (matching management template).
    Includes: line chart, demographics tables, income/occupation cards,
    restaurant/pub tables, transport section, and Google Maps embed.
    """
    try:
        from bokeh.plotting import figure
        from bokeh.embed import file_html
        from bokeh.resources import CDN
        from bokeh.models import (
            NumeralTickFormatter, HoverTool, ColumnDataSource,
            Div, Legend, LegendItem, DatetimeTickFormatter,
            DataRange1d, CustomJS, CheckboxGroup,
            TableColumn as BokehTableColumn, StringFormatter,
            HTMLTemplateFormatter
        )
        from bokeh.models.widgets import DataTable
        from bokeh.layouts import column, row
        import pandas as pd
        import numpy as np
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Missing library: {e}")

    postcode = request_body.postcode.upper()
    dates_raw = request_body.dates
    sales = request_body.sales
    granularity = request_body.granularity.capitalize()
    features = request_body.features
    dd = request_body.display_data

    # ── Resolve geographic breadcrumb from features ────────────────────────────
    town = features.get("Town", "") or dd.get("town", "") or postcode
    breadcrumb = f"UK, England, {town}, {postcode}" if town and town != postcode else f"UK, {postcode}"

    # ── Parse dates into datetime objects for proper datetime axis ─────────────
    parsed_dates = []
    for d in dates_raw:
        try:
            parsed_dates.append(pd.to_datetime(d))
        except Exception:
            parsed_dates.append(None)

    # Filter out unparseable dates
    valid_pairs = [(d, s) for d, s in zip(parsed_dates, sales) if d is not None]
    if valid_pairs:
        dates_dt = [p[0] for p in valid_pairs]
        sales_vals = [p[1] for p in valid_pairs]
    else:
        # Fallback: use string-based x_range
        dates_dt = list(range(len(sales)))
        sales_vals = sales

    # ── Average prediction line ───────────────────────────────────────────────
    avg_pred = float(np.mean(sales_vals)) if sales_vals else 0

    # ── Build the main ColumnDataSource ────────────────────────────────────────
    source = ColumnDataSource(data=dict(
        Date=dates_dt,
        Prediction=sales_vals,
        Postcode=[postcode] * len(sales_vals),
        AveragePrediction=[avg_pred] * len(sales_vals),
    ))

    # ══════════════════════════════════════════════════════════════════════════
    #  1. HEADER DIV  (Geographic breadcrumb)
    # ══════════════════════════════════════════════════════════════════════════
    header_div = Div(text=f"<h1>{breadcrumb}</h1>", width=800)

    # ══════════════════════════════════════════════════════════════════════════
    #  2. CHECKBOX GROUP  (Postcode toggle – single series for now)
    # ══════════════════════════════════════════════════════════════════════════
    checkbox = CheckboxGroup(labels=[postcode], active=[0])

    # ══════════════════════════════════════════════════════════════════════════
    #  3. LINE CHART  (1500x800 with DatetimeAxis and HoverTool)
    # ══════════════════════════════════════════════════════════════════════════
    p = figure(
        title="Predictions of Postcode with Demographics",
        width=1500,
        height=800,
        x_axis_type="datetime",
        x_axis_label="Date",
        y_axis_label="Prediction",
        tools="pan,wheel_zoom,box_zoom,save,reset,help",
        toolbar_location="right",
    )

    line_renderer = p.line(
        'Date', 'Prediction', source=source,
        line_color="#1f77b4", line_width=2,
    )

    # Legend
    legend = Legend(items=[LegendItem(label=postcode, renderers=[line_renderer])])
    p.add_layout(legend)

    # Hover tool with datetime formatting
    hover = HoverTool(
        renderers=[line_renderer],
        tooltips=[
            ("Date", "@Date{%F}"),
            ("Prediction", "@Prediction{0.000}"),
            ("Average Prediction", "@AveragePrediction{0.000}"),
        ],
        formatters={"@Date": "datetime"},
        mode="vline",
    )
    p.add_tools(hover)

    # JS callback for checkbox toggle
    callback = CustomJS(
        args=dict(lines=[line_renderer], checkbox=checkbox),
        code="""
        for (let i = 0; i < lines.length; i++) {
            lines[i].visible = checkbox.active.includes(i);
        }
        """,
    )
    checkbox.js_on_change("active", callback)

    # ══════════════════════════════════════════════════════════════════════════
    #  4. DEMOGRAPHICS DataTable
    # ══════════════════════════════════════════════════════════════════════════
    demo_keys = [
        "postcode", "population", "households", "avg_household_income",
        "unemployment_rate", "rateable_value", "workplace_to_resident_ratio", 
        "ethnic_diversity_index", "working", "unemployed", "ab", "c1/c2", "de",
        "white", "non-white", "Town",
    ]
    demo_labels = []
    demo_values = []
    for k in demo_keys:
        v = features.get(k, "")
        if k == "postcode":
            v = postcode
        elif k == "Town" and not v:
            v = town
        demo_labels.append(k)
        demo_values.append(str(v) if v != "" else "N/A")

    demo_source = ColumnDataSource(data=dict(
        Demographics=demo_labels,
        Values=demo_values,
    ))
    demo_columns = [
        BokehTableColumn(field="Demographics", title="Demographics", formatter=StringFormatter()),
        BokehTableColumn(field="Values", title="Values", formatter=StringFormatter()),
    ]
    demo_heading = Div(text="<h3>Postcode area Demographics</h3>", width=800)
    demo_table = DataTable(source=demo_source, columns=demo_columns, width=800, height=min(400, 30 * len(demo_labels) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  5. ETHNICITY / RELIGION / AGE / HOUSEHOLD DataTable
    # ══════════════════════════════════════════════════════════════════════════
    ethnicity_data = dd.get("ethnicity", {})
    eth_sections = ethnicity_data.get("sections", {})
    eth_names = []
    eth_pcts = []
    for section_name in ["Ethnicity", "Religion", "Age", "Household"]:
        items = eth_sections.get(section_name, [])
        if isinstance(items, list):
            for item in items:
                name = item.get("name", "")
                pct = item.get("pct", "")
                if name:
                    eth_names.append(str(name))
                    eth_pcts.append(float(pct) if pct != "" else 0.0)

    eth_source = ColumnDataSource(data=dict(Demographics=eth_names, Percentage=eth_pcts))

    # Color-coded formatter (key demographics get highlighted)
    eth_formatter = HTMLTemplateFormatter(template="""
        <div style="background:<%= 
            (function colorfromint(){
                if(Demographics=='White British'){ return('#ec3219')}
                if(Demographics=='Other White'){ return('#ec3219')}
                if(Demographics=='Pakistani'){ return('#008000')}
                if(Demographics=='Indian'){ return('#f77000')}
                if(Demographics=='Aged 20 To 39'){ return('#FFD700')}
                if(Demographics=='Aged 20 to 39'){ return('#FFD700')}
            }()) %>;"> 
        <%= value %>
        </div>
    """)
    eth_columns = [
        BokehTableColumn(field="Demographics", title="Demographics", formatter=eth_formatter),
        BokehTableColumn(field="Percentage", title="Percentage", formatter=StringFormatter()),
    ]
    eth_heading = Div(text="<h3>Ethnicity, Religion, Age, Households</h3>", width=800)
    eth_table = DataTable(source=eth_source, columns=eth_columns, width=800, height=min(500, 30 * len(eth_names) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  6. RESTAURANTS DataTable
    # ══════════════════════════════════════════════════════════════════════════
    restaurants = dd.get("amenities", {}).get("restaurants", [])
    rest_names = [r.get("name", "") for r in restaurants[:20]] if isinstance(restaurants, list) else []
    rest_dists = [r.get("distance", "") for r in restaurants[:20]] if isinstance(restaurants, list) else []

    rest_source = ColumnDataSource(data=dict(Restaurant=rest_names, Distance=rest_dists))
    rest_columns = [
        BokehTableColumn(field="Restaurant", title="Restaurant", formatter=StringFormatter()),
        BokehTableColumn(field="Distance", title="Distance", formatter=StringFormatter()),
    ]
    rest_heading = Div(text="<h3>Restaurants Near Postcode</h3>", width=800)
    rest_table = DataTable(source=rest_source, columns=rest_columns, width=800, height=min(500, 30 * len(rest_names) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  7. PUBS DataTable
    # ══════════════════════════════════════════════════════════════════════════
    pubs = dd.get("amenities", {}).get("pubs", [])
    pub_names = [r.get("name", "") for r in pubs[:20]] if isinstance(pubs, list) else []
    pub_dists = [r.get("distance", "") for r in pubs[:20]] if isinstance(pubs, list) else []

    pub_source = ColumnDataSource(data=dict(Pub=pub_names, Distance=pub_dists))
    pub_columns = [
        BokehTableColumn(field="Pub", title="Pub", formatter=StringFormatter()),
        BokehTableColumn(field="Distance", title="Distance", formatter=StringFormatter()),
    ]
    pub_heading = Div(text="<h3>Bars, pubs, clubs</h3>", width=800)
    pub_table = DataTable(source=pub_source, columns=pub_columns, width=800, height=min(600, 30 * len(pub_names) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  8. INCOME SECTION (Styled card Div)
    # ══════════════════════════════════════════════════════════════════════════
    affluence = dd.get("affluence", {})
    income_pa = affluence.get("income_pa", features.get("avg_household_income", 0))
    affluence_rating = affluence.get("rating", "N/A")

    income_div = Div(width=800, text=f"""
        <h1>Income Section</h1>
        <div style="border: 1px solid #ccc; border-radius: 8px; padding: 15px; background-color: orange; color: black;">
            <p style="margin: 0; font-weight: bold;">Mean household income estimate before tax</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                <p style="margin: 0; font-size: 24px; font-weight: bold;">£{income_pa:,} p/a</p>
                <span style="font-size: 24px; font-weight: bold;">{affluence_rating}</span>
            </div>
        </div>
    """)

    # ══════════════════════════════════════════════════════════════════════════
    #  9. OCCUPATION SECTION (Styled card + DataTable)
    # ══════════════════════════════════════════════════════════════════════════
    occupation = dd.get("occupation", {})
    occ_labels_list = []
    occ_pcts_list = []
    if isinstance(occupation, dict):
        label_map = {
            "managerial and professional": "Managerial and professional",
            "intermediate occupations": "Intermediate occupations",
            "routine and manual": "Routine and manual",
            "never worked": "Never worked, long-term unemployed",
            "full-time students": "Full-time students",
        }
        for k, v in occupation.items():
            occ_labels_list.append(label_map.get(k, k.replace("_", " ").title()))
            occ_pcts_list.append(f"{v}%")

    occ_div = Div(width=800, text="""
        <h1>Occupation section</h1>
        <div style="border: 1px solid #ccc; border-radius: 6px; padding: 15px; background-color: PaleVioletRed; color: black;">
            <p style="margin: 0; font-weight: bold;">Occupation</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                <p style="margin: 0; font-size: 18px;">Occupation breakdown for this postcode area.</p>
            </div>
        </div>
    """)

    occ_source = ColumnDataSource(data=dict(Occupation=occ_labels_list, Percentage=occ_pcts_list))
    occ_fmt = HTMLTemplateFormatter(template="""
        <div style="background:<%= 
            (function colorfromint(){
                if(Occupation=='Full-time students'){ return('#FF7F50')}
            }()) %>;"> 
        <%= value %>
        </div>
    """)
    occ_columns = [
        BokehTableColumn(field="Occupation", title="Occupation", formatter=occ_fmt),
        BokehTableColumn(field="Percentage", title="Percentage", formatter=StringFormatter()),
    ]
    occ_table = DataTable(source=occ_source, columns=occ_columns, width=800, height=min(200, 30 * len(occ_labels_list) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  10. TRANSPORT SECTION (SVG icon heading + DataTable)
    # ══════════════════════════════════════════════════════════════════════════
    transport = dd.get("transport", {})
    transport_score = transport.get("score", "N/A")
    transport_zone = transport.get("zone", "N/A")
    stations = transport.get("stations", [])

    transport_svg_icon = (
        '<svg width="20" height="20" viewBox="0 0 32 24">'
        '<path d="M16 0A12 12 0 004.68 8h4.4a8 8 0 0113.8 0h4.4A12 12 0 0016 0z'
        'M27.8 10h-4.08a7.86 7.86 0 01.26 2 8.23 8.23 0 01-.25 2h4.08a11.9 11.9 0 000-4z'
        'M16 19.98a8 8 0 01-6.91-4h-4.4a12 12 0 0022.62 0h-4.4a8 8 0 01-6.9 4z'
        'm-8-8a7.86 7.86 0 01.26-2H4.17a11.9 11.9 0 000 4h4.08a8.23 8.23 0 01-.25-2z"'
        ' fill="#ED7C23"></path>'
        '<path d="M29.98 10H2a2 2 0 00-2 2 2 2 0 002 2h27.98a2 2 0 002-2 2 2 0 00-2-2z"'
        ' fill="#213e90"></path></svg>'
    )

    transport_heading = Div(width=800, text=f"""
        <h1>{transport_svg_icon} Transport Section</h1>
    """)

    # Transport score table (single row)
    transport_score_source = ColumnDataSource(data={
        "connectivity to public transport": [f"{transport_score}/9" if transport_score != "N/A" else "N/A"],
        "travel zone": [str(transport_zone)],
    })
    transport_score_cols = [
        BokehTableColumn(field="connectivity to public transport", title="connectivity to public transport", formatter=StringFormatter()),
        BokehTableColumn(field="travel zone", title="travel zone", formatter=StringFormatter()),
    ]
    transport_score_table = DataTable(source=transport_score_source, columns=transport_score_cols, width=800, height=50)

    # Stations detailed table
    station_names = [s.get("name", "") for s in stations[:10]] if isinstance(stations, list) else []
    station_dists = [f"{s.get('distance', '')} mi" for s in stations[:10]] if isinstance(stations, list) else []
    station_types = [s.get("type", "") for s in stations[:10]] if isinstance(stations, list) else []

    station_source = ColumnDataSource(data=dict(
        station_name=station_names,
        distance=station_dists,
        lines=station_types,
    ))
    station_columns = [
        BokehTableColumn(field="station_name", title="station_name", formatter=StringFormatter()),
        BokehTableColumn(field="distance", title="distance", formatter=StringFormatter()),
        BokehTableColumn(field="lines", title="lines", formatter=StringFormatter()),
    ]
    station_table = DataTable(source=station_source, columns=station_columns, width=1000, height=min(300, 30 * len(station_names) + 40))

    # ══════════════════════════════════════════════════════════════════════════
    #  11. GOOGLE MAPS EMBED
    # ══════════════════════════════════════════════════════════════════════════
    maps_query = f"{town}+{postcode.replace(' ', '+')}+,+UK" if town else f"{postcode.replace(' ', '+')}+,+UK"
    maps_heading = Div(text="<h2>Google Maps Section</h2>", width=300, height=100)
    maps_div = Div(width=1000, height=800, text=f"""
        <div class="mapouter"><div class="gmap_canvas">
            <iframe width="1200" height="800" id="gmap_canvas"
                src="https://maps.google.com/maps?q={maps_query}&t=&z=17&ie=UTF8&iwloc=&output=embed"
                frameborder="0" scrolling="no" marginheight="0" marginwidth="0">
            </iframe>
        </div></div>
    """)

    # ══════════════════════════════════════════════════════════════════════════
    #  ASSEMBLE FINAL LAYOUT  (Column of all components)
    # ══════════════════════════════════════════════════════════════════════════
    spacer = Div(text="", width=800, height=10)

    layout = column(
        header_div,
        checkbox,
        p,
        row(),                     # Spacer row
        demo_heading,
        demo_table,
        eth_heading,
        eth_table,
        rest_heading,
        rest_table,
        pub_heading,
        pub_table,
        income_div,
        occ_div,
        occ_table,
        transport_heading,
        transport_score_table,
        station_table,
        maps_heading,
        maps_div,
    )

    report_title = f"Predictions Plot — {postcode}"
    html_output = file_html(layout, CDN, report_title)
    return HTMLResponse(content=html_output)
