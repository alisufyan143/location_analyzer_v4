import pytest
from httpx import AsyncClient, ASGITransport
import logging

from sqlalchemy import text
from location_analyzer.api.main import app
from location_analyzer.data.database import create_db_engine, create_session_factory, init_db
from location_analyzer.data.models import Base
from location_analyzer.data.repository import PostcodeRepository

logger = logging.getLogger(__name__)

# Valid real-world UK postcodes for Halal Fast Food branches (Fresh Scrapes)
TEST_POSTCODES = [
    "B20 3HS",  # Dixy Chicken Birmingham (Aston Lane)
    "LS11 5HN", # Chicken Cottage Leeds (Beeston)
    "HP20 2ER"  # Chicken Cottage Aylesbury
]

# Invalid / Edge-case postcodes
INVALID_POSTCODES = [
    "INVALID123", # Gibberish
    "AB1 2CD",    # Technically valid format, but often doesn't exist
    "",           # Empty string
]

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure the test database is clean before running E2E tests."""
    engine = create_db_engine()
    Base.metadata.create_all(engine)  # Explicitly force table creation for the test environment
    
    # Setup: Clear the specific test postcodes before running the test to guarantee cache miss
    SessionFactory = create_session_factory(engine)
    with SessionFactory() as session:
        repo = PostcodeRepository(session)
        for pc in TEST_POSTCODES:
            logger.info(f"Test Setup: Attempting to purge {pc} from cache")
            repo.delete_postcode(pc)
        session.commit()
    
    yield
    
    # Teardown: Clear the specific test postcodes from SQLite immediately after the test runs
    with SessionFactory() as session:
        repo = PostcodeRepository(session)
        for pc in TEST_POSTCODES:
            logger.info(f"Test Teardown: Attempting to purge {pc} from cache")
            repo.delete_postcode(pc)
        session.commit()

@pytest.mark.live
@pytest.mark.asyncio
async def test_e2e_full_prediction_pipeline():
    """
    Rigorously tests the entire stack:
    1. Validates input
    2. Triggers live playwright scrape (Phase 3 & 5)
    3. Runs the data through the XGBoost ML Pipeline (Phase 4)
    4. Validates the output schema (Daily/Weekly/Monthly arrays)
    """
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=180.0) as client:
            # Test 1: Standard Live Scrape
            postcode = TEST_POSTCODES[0] # "B20 3HS"
            logger.info(f"E2E Test starting for LIVE postcode: {postcode}")
            
            response = await client.post(
                "/predict",
                json={"postcode": postcode, "force_refresh": False}
            )
            
            assert response.status_code == 200, f"Live scrape failed: {response.text}"
            data = response.json()
        
            # Validate Core Schema
            assert data["postcode"] == postcode.upper()
            assert "predicted_sales" in data
            assert data["source"] == "live_scrape", "Expected live_scrape for a fresh DB"
            
            # Validate Features extracted
            features = data["features"]
            if "Transport_Accessibility_Score" in features:
                assert features["Transport_Accessibility_Score"] is None or features["Transport_Accessibility_Score"] >= 0
            
            # Validate ML Time-Series structure (Phase 6 Enhancement)
            time_series = data["time_series"]
            assert "daily" in time_series
            assert "weekly" in time_series
            assert "monthly" in time_series
            
            assert len(time_series["monthly"]) == 12, "Forecast should predict 12 months"
            assert len(time_series["weekly"]) >= 52, "Forecast should predict ~52 weeks"
            
            # Test 2: Verify SQLite Caching works immediately after
            logger.info(f"E2E Test: Verifying CACHE hit for {postcode}")
            response_cache = await client.post(
                "/predict",
                json={"postcode": postcode, "force_refresh": False}
            )
            assert response_cache.status_code == 200
            data_cache = response_cache.json()
            assert data_cache["source"] == "database_cache", "The second call MUST return from the local SQLite cache"
            assert data_cache["predicted_sales"] == data["predicted_sales"], "Cache output must exactly match live output"
            
            # Test 3: Verify the "Force Live Scrape" Bypass (Phase 6 Enhancement)
            logger.info(f"E2E Test: Verifying FORCE_REFRESH bypass for {postcode}")
            response_force = await client.post(
                "/predict",
                json={"postcode": postcode, "force_refresh": True}
            )
            assert response_force.status_code == 200
            data_force = response_force.json()
            assert data_force["source"] == "live_scrape", "Force refresh must bypass SQLite cache"
        
@pytest.mark.asyncio
async def test_e2e_invalid_inputs():
    """
    Tests the error formatting and API resilience to bad or empty postcodes.
    """
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for invalid_pc in INVALID_POSTCODES:
                response = await client.post(
                    "/predict",
                    json={"postcode": invalid_pc}
                )
                # Depending on if Pydantic catches it early (422) or if the pipeline fails inside (400/500)
                assert response.status_code in [400, 422, 500], f"Invalid postcode {invalid_pc} should not return 200 OK"
                assert "detail" in response.json()

@pytest.mark.live
@pytest.mark.asyncio
async def test_e2e_geographical_extraction():
    """
    Specifically tests the Phase 6 PDF Export prerequisite: 
    Does the backend properly extract Region/District/Ward from Postcodes.io?
    """
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=180.0) as client:
            # Use a distinct postcode to avoid cache interference 
            response = await client.post(
                "/predict",
                json={"postcode": "SL1 1XQ", "force_refresh": True}
            )
            
            assert response.status_code == 200
            data = response.json()
        features = data["features"]
        
        # Verify the localized strings are present for the PDF builder
        assert "region" in features, "API missing Region string"
        assert "district" in features, "API missing District string"
        assert "ward" in features, "API missing Ward string"

        assert features["region"] is not None
        assert features["district"] is not None
        assert features["ward"] is not None
