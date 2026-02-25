import asyncio
import calendar
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from location_analyzer.api.schemas import PredictRequest, PredictResponse, TimeSeriesPrediction
from location_analyzer.pipeline.inference_pipeline import InferencePipeline
from location_analyzer.data.repository import PostcodeRepository

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_session_factory(request: Request):
    return getattr(request.app.state, "session_factory", None)


@router.post("/predict", response_model=PredictResponse)
async def predict_sales(request_body: PredictRequest, request: Request):
    """
    Predict sales: use DB if we have features for this postcode, else scrape then persist.
    Never holds a DB connection during scraping or model inference (no bottleneck).
    """
    model_service = request.app.state.model_service
    if not model_service:
        raise HTTPException(status_code=500, detail="PredictionService is offline. ML artifacts could not be loaded on startup.")

    postcode = request_body.postcode.upper().strip()
    logger.info("Received Prediction Request for: %s", postcode)

    session_factory = _get_session_factory(request)
    features = None

    # 1) Try DB first (single short read; no connection held during scrape)
    if session_factory:
        with session_factory() as session:
            repo = PostcodeRepository(session)
            features = repo.get_features_for_postcode(postcode)

    # 2) If not in DB, scrape in thread (no DB held)
    if features is None:
        pipeline = InferencePipeline()
        features = await asyncio.to_thread(pipeline.run, postcode)
        if not features:
            raise HTTPException(status_code=404, detail=f"Could not extract any data for postcode: {postcode}")

        # 3) Persist scraped result in its own short transaction
        if session_factory:
            with session_factory() as session:
                repo = PostcodeRepository(session)
                repo.save_scraped_result(postcode, features)
                session.commit()

    if request_body.branch_name:
        features["Branch Name"] = request_body.branch_name

    # 4) Time series + model (no DB held)
    # Training target in notebook is daily Total Sale (one row per date). One prediction = daily sales.
    current_date = datetime.now()
    features_list = []
    dates_list = []
    month_days = []  # days in each month for daily -> monthly conversion
    for i in range(12):
        month_val = current_date.month + i
        y = current_date.year + (month_val - 1) // 12
        m = (month_val - 1) % 12 + 1
        pred_date = datetime(y, m, 1)
        _, days_in_month = calendar.monthrange(y, m)
        features_list.append({**features.copy(), "Date": pred_date.strftime("%Y-%m-%d")})
        dates_list.append(pred_date.strftime("%b %Y"))
        month_days.append(days_in_month)

    predictions = model_service.predict(features_list)
    # Convert daily prediction to monthly: daily * days in that month
    predictions_monthly = [p * days for p, days in zip(predictions, month_days)]
    time_series = [
        TimeSeriesPrediction(date=d, predicted_sales=round(p, 2))
        for d, p in zip(dates_list, predictions_monthly)
    ]

    # 5) Store prediction in DB (short write transaction; store monthly)
    if session_factory and time_series:
        median_pred = time_series[0].predicted_sales
        preds = [t.predicted_sales for t in time_series]
        with session_factory() as session:
            repo = PostcodeRepository(session)
            repo.upsert_postcode(
                postcode,
                prediction=median_pred,
                min_prediction=min(preds) if preds else None,
                max_prediction=max(preds) if preds else None,
            )
            session.commit()

    return PredictResponse(
        postcode=postcode,
        predicted_sales=time_series[0].predicted_sales,
        features=features,
        time_series=time_series,
    )
