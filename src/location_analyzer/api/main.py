import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from location_analyzer.api.routes import router
from location_analyzer.ml.predict import PredictionService
from location_analyzer.config import settings
from location_analyzer.data.database import create_db_engine, create_session_factory, init_db
from location_analyzer.logging_config import setup_logging

# Initialize structured logging immediately
setup_logging(level=settings.logging.level, log_file=settings.logging.file)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data dir exists (for SQLite file at data/location_analyzer.db)
    settings.paths.ensure_dirs()

    # Database: create tables and session factory (short-lived sessions per request)
    try:
        engine = create_db_engine()
        init_db(engine)
        app.state.session_factory = create_session_factory(engine)
        logger.info("Database initialized; session factory attached.")
    except Exception as e:
        logger.error("Database init failed: %s. Predict will not persist.", e)
        app.state.session_factory = None

    # ML model (loaded once)
    model_dir = settings.ml.models_dir
    logger.info("Initializing PredictionService from %s...", model_dir)
    try:
        app.state.model_service = PredictionService(model_dir=str(model_dir))
        logger.info("PredictionService initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize PredictionService: %s", e)
        app.state.model_service = None

    yield
    # Shutdown: nothing to close (sessions are request-scoped)

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
