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
    with patch('location_analyzer.pipeline.inference_pipeline.DemographicsScraper') as mock_demo, \
         patch('location_analyzer.pipeline.inference_pipeline.CrystalRoofScraper') as mock_cr:
         
        mock_demo.return_value.scrape.return_value = {
            "population": 50000, 
            "avg_household_income": 40000,
            "working": 30000,
            "unemployed": 2000,
            "ab": 8000,
            "c1_c2": 15000,
            "de": 5000,
            "non_white": 5000
        }
        
        mock_cr.return_value.scrape.return_value = {
            "Distance_to_Nearest_Station": 0.5,
            "Nearby_Station_Count": 3,
            "Nearest_Station_Type": "Underground",
            "Transport_Accessibility_Score": 5
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
        assert data["predicted_sales"] >= 0 # XGBoost is designed to predict positive sales
        assert data["currency"] == "£"
        
        # Verify 12-month time series generation
        time_series = data["time_series"]
        assert isinstance(time_series, list)
        assert len(time_series) == 12
        assert time_series[0]["predicted_sales"] == data["predicted_sales"]
        assert "date" in time_series[0]
        
        # Verify mapping worked
        features = data["features"]
        assert features["c1/c2"] == 15000
        assert features["non-white"] == 5000
        assert features["Branch Name"] == "Test Branch"
        
def test_predict_endpoint_missing_postcode(mock_scrapers, mock_model):
    with TestClient(app) as client:
        payload = {
            "branch_name": "Test Branch"
        }
        response = client.post("/predict", json=payload)
        assert response.status_code == 422 # Standard FastAPI validation error
