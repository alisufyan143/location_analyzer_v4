import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from location_analyzer.api.routes import router
from location_analyzer.ml.predict import PredictionService
from location_analyzer.config import settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the heavy ML model and Scikit-Learn pipelines once
    model_dir = settings.paths.data_dir.replace('data', 'models')
    # Because config.py doesn't have a direct attribute for models_dir natively available on top level. 
    # But wait, settings has `ml.models_dir`.
    
    # Actually, let's use the explicit path from settings
    model_dir = settings.ml.models_dir
    
    logger.info(f"Initializing PredictionService from {model_dir}...")
    try:
        app.state.model_service = PredictionService(model_dir=str(model_dir))
        logger.info("PredictionService initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize PredictionService: {e}")
        # We don't raise here so the app can still boot and serve healthchecks,
        # but the /predict endpoint will 500.
        app.state.model_service = None
        
    yield
    # Shutdown logic (if any) goes here

app = FastAPI(
    title="Location Analyzer API",
    description="API for scraping demographics and predicting fast food sales.",
    version="2.0.0",
    lifespan=lifespan
)

# Allow all CORS for the frontend explicitly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "model_loaded": app.state.model_service is not None}
