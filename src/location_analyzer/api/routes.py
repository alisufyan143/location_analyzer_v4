import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from location_analyzer.api.schemas import PredictRequest, PredictResponse, TimeSeriesPrediction
from location_analyzer.pipeline.inference_pipeline import InferencePipeline

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/predict", response_model=PredictResponse)
async def predict_sales(request_body: PredictRequest, request: Request):
    """
    Endpoint to trigger the live scraping sequence and return a Median Ensemble prediction
    spanning Random Forest, XGBoost, LightGBM, and CatBoost.
    """
    model_service = request.app.state.model_service
    if not model_service:
        raise HTTPException(status_code=500, detail="PredictionService is offline. ML artifacts could not be loaded on startup.")
        
    postcode = request_body.postcode.upper().strip()
    logger.info(f"Received Prediction Request for: {postcode}") 
    
    try:
        # Step 1: Run the scraping pipeline in a thread pool to avoid
        # blocking uvicorn's async event loop (Playwright uses sync API)
        pipeline = InferencePipeline()
        features = await asyncio.to_thread(pipeline.run, postcode)
        
        if not features:
            raise HTTPException(status_code=404, detail=f"Could not extract any data for postcode: {postcode}")
            
        # Optional: Add the requested branch_name
        if request_body.branch_name:
            features['Branch Name'] = request_body.branch_name
            
        # Step 2: Time Series Generation
        # We artificially generate 12 distinct dates for this exact location over the next year
        # to force the XGBoost model to account for Month/Seasonality variances.
        current_date = datetime.now()
        features_list = []
        dates_list = []
        
        for i in range(12):
            m = current_date.month + i
            y = current_date.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            
            # Predict for the 1st day of that future month
            pred_date = datetime(y, m, 1)
            f_copy = features.copy()
            f_copy['Date'] = pred_date.strftime("%Y-%m-%d")
            
            features_list.append(f_copy)
            dates_list.append(pred_date.strftime("%b %Y"))

        # Feed the batch of 12 records into the ML Model Feature Engineering pipeline simultaneously
        predictions = model_service.predict(features_list)
        
        # Format the time series graph
        time_series = [
            TimeSeriesPrediction(date=d, predicted_sales=round(p, 2))
            for d, p in zip(dates_list, predictions)
        ]
        
        return PredictResponse(
            postcode=postcode,
            predicted_sales=time_series[0].predicted_sales,
            features=features,
            time_series=time_series
        )
        
    except Exception as e:
        logger.error(f"Inference pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
