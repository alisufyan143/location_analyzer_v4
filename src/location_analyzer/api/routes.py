import asyncio
import calendar
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from location_analyzer.api.schemas import PredictRequest, PredictResponse, TimeSeriesPrediction, GranularTimeSeries
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

    now = datetime.now()
    # Start from today, but the predictions are month-based.
    # We'll get 13 months just to be safe if today is late in the month.
    monthly_rates = {}
    
    # Pre-calculate base predictions for each month
    pred_features = []
    month_keys = []
    for i in range(13):
        target_date = now + pd.DateOffset(months=i)
        y, m = target_date.year, target_date.month
        pred_features.append({**features.copy(), "Date": f"{y}-{m:02d}-01"})
        month_keys.append((y, m))

    raw_preds = model_service.predict(pred_features)
    for key, p in zip(month_keys, raw_preds):
        monthly_rates[key] = p

    # Daily sequence: Today until end of Month 12
    # End date is start of Month 13 - 1 day
    end_month_date = now + pd.DateOffset(months=12)
    last_day_of_12th = datetime(end_month_date.year, end_month_date.month, 1) + pd.DateOffset(months=1) - timedelta(days=1)
    
    daily_ts = []
    curr = now
    while curr <= last_day_of_12th:
        rate = monthly_rates.get((curr.year, curr.month), raw_preds[-1])
        daily_ts.append(TimeSeriesPrediction(
            date=curr.strftime("%Y-%m-%d"), 
            predicted_sales=round(rate, 2)
        ))
        curr += timedelta(days=1)

    # Weekly sequence: Monday-based weeks starting from the week of 'now'
    weekly_ts = []
    # Find start of current week (Monday)
    curr_week_start = now - timedelta(days=now.weekday())
    while curr_week_start <= last_day_of_12th:
        week_sum = 0
        for i in range(7):
            day = curr_week_start + timedelta(days=i)
            rate = monthly_rates.get((day.year, day.month), raw_preds[-1])
            week_sum += rate
        
        # Label as 'Week of {Date}'
        weekly_ts.append(TimeSeriesPrediction(
            date=curr_week_start.strftime("%Y-%m-%d"),
            predicted_sales=round(week_sum, 2)
        ))
        curr_week_start += timedelta(days=7)

    # Monthly sequence: Current month + 11
    monthly_ts = []
    for i in range(12):
        target_date = now + pd.DateOffset(months=i)
        y, m = target_date.year, target_date.month
        rate = monthly_rates[(y, m)]
        _, days = calendar.monthrange(y, m)
        monthly_ts.append(TimeSeriesPrediction(
            date=target_date.strftime("%b %Y"),
            predicted_sales=round(rate * days, 2)
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
