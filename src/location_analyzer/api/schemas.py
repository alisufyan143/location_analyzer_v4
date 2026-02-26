from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, Optional, List

class TimeSeriesPrediction(BaseModel):
    date: str
    predicted_sales: float

class PredictRequest(BaseModel):
    """Request schema for predicting location sales."""
    postcode: str = Field(..., description="The full UK postcode to analyze.")
    branch_name: Optional[str] = Field(None, description="Optional name of the branch.")
    force_refresh: bool = Field(False, description="If true, bypasses DB cache and forces a live scrape.")

class GranularTimeSeries(BaseModel):
    """Daily, Weekly, and Monthly 12-month projections."""
    daily: List[TimeSeriesPrediction]
    weekly: List[TimeSeriesPrediction]
    monthly: List[TimeSeriesPrediction]

class PredictResponse(BaseModel):
    """Response schema returning the £ sales prediction and the features used."""
    postcode: str
    predicted_sales: float
    currency: str = "£"
    features: Dict[str, Any] = Field(..., description="The scraped/compiled features used by the ML model.")
    display_data: Dict[str, Any] = Field(default_factory=dict, description="Rich CrystalRoof data for dashboard display (amenities, ethnicity, occupation, etc.).")
    time_series: GranularTimeSeries = Field(..., description="12-month forecasting predictions (Daily/Weekly/Monthly).")

    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "postcode": "SW1A 1AA",
                "predicted_sales": 1500.50,
                "currency": "£",
                "features": {
                    "population": 50000,
                    "avg_household_income": 45000
                },
                "time_series": [
                    {"date": "Jan 2026", "predicted_sales": 1500.50},
                    {"date": "Feb 2026", "predicted_sales": 1520.25}
                ]
            }
        }
    )
