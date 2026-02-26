import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Important: we patch the scrapers and prediction service so we don't
# run real Playwright browsers or load the actual .pkl models during pure unit testing.
from location_analyzer.api.main import app

# This override is only used if we use normal FastAPI dependency injection, 
# but we used app.state.model_service instead, so we'll patch that directly.

@pytest.fixture
def mock_scrapers():
    # Pipeline calls .scrape_with_fallback() — mock that method, not .scrape()
    with patch('location_analyzer.pipeline.inference_pipeline.DemographicsScraper') as mock_demo, \
         patch('location_analyzer.pipeline.inference_pipeline.CrystalRoofScraper') as mock_cr:

        # Values are in 0.0-1.0 fraction scale (matching real DemographicsScraper output)
        mock_demo.return_value.scrape_with_fallback.return_value = {
            "population": 50000,
            "households": 20000,
            "avg_household_income": 40000,
            "working": 0.60,
            "unemployed": 0.04,
            "unemployment_rate": 0.04,
            "ab": 0.16,
            "c1_c2": 0.30,
            "de": 0.10,
            "white": 0.85,
            "non_white": 0.15,
        }

        mock_cr.return_value.scrape_with_fallback.return_value = {
            "transport": {
                "score": 5,
                "stations": [
                    {"name": "Westminster", "distance": 0.5, "type": "Underground", "lines": ["Jubilee"]}
                ]
            }
        }

        yield mock_demo, mock_cr

@pytest.fixture
def mock_model():
    # We leave the real PredictionService instantiation intact in the lifespan, 
    # but we don't necessarily need to mock the model itself! The TestClient will run the true ML inference.
    pass

def test_health_check():
    client = TestClient(app)
    # the healthcheck doesn't use the db, but app startup might fail 
    # to load models. TestClient skips the lifespan by default without 'with TestClient(app)' context
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

def test_predict_endpoint_success(mock_scrapers, mock_model):
    # Also mock the DB repository so stale real-DB data doesn't shadow our mock scraper.
    # get_features_for_postcode returns None → forces the pipeline to scrape (mock path).
    with patch('location_analyzer.api.routes.PostcodeRepository') as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_features_for_postcode.return_value = None  # force scrape path
        mock_repo.save_scraped_result.return_value = None         # prevent DB writes
        mock_repo.upsert_postcode.return_value = MagicMock()
        mock_repo_cls.return_value = mock_repo

        with TestClient(app) as client:
            payload = {
                "postcode": "SW1A 1AA",
                "branch_name": "Test Branch"
            }
            response = client.post("/predict", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["postcode"] == "SW1A 1AA"
            assert isinstance(data["predicted_sales"], float)
            assert data["predicted_sales"] >= 0
            assert data["currency"] == "£"

            # Verify 12-month time series generation
            time_series = data["time_series"]
            assert isinstance(time_series, list)
            assert len(time_series) == 12
            assert time_series[0]["predicted_sales"] == data["predicted_sales"]
            assert "date" in time_series[0]

            # Verify key renaming worked (underscore → slash/dash as model expects)
            features = data["features"]
            assert "c1/c2" in features
            assert "non-white" in features
            assert isinstance(features["c1/c2"], float)
            assert isinstance(features["non-white"], float)
            assert features["Branch Name"] == "Test Branch"
        
def test_predict_endpoint_missing_postcode(mock_scrapers, mock_model):
    with TestClient(app) as client:
        payload = {
            "branch_name": "Test Branch"
        }
        response = client.post("/predict", json=payload)
        assert response.status_code == 422 # Standard FastAPI validation error
