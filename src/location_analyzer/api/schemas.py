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
    from_month: Optional[int] = Field(None, ge=1, le=12, description="Start month (1-12). Defaults to current month.")
    from_year: Optional[int] = Field(None, ge=2020, le=2028, description="Start year. Defaults to current year.")
    to_month: Optional[int] = Field(None, ge=1, le=12, description="End month (1-12). Defaults to 12 months from now.")
    to_year: Optional[int] = Field(None, ge=2020, le=2028, description="End year. Defaults to 12 months from now.")
    inflate_sales: bool = Field(False, description="If true, adds weekly inflation adjustment to predictions.")
    inflate_amount: Optional[float] = Field(None, ge=0, description="Weekly inflation amount in £. Used only when inflate_sales is true.")
    
    # [V4 Integration] Situational & Contextual Overrides
    is_logistics_strike: bool = Field(False, description="Simulate a logistics/supply chain strike.")
    is_delivery_crackdown: bool = Field(False, description="Simulate a local delivery/parking crackdown.")
    inferred_brand_override: Optional[int] = Field(None, description="Manually set the brand ID (1-7). If None, it is inferred from branch_name.")
    days_since_open: Optional[int] = Field(1000, description="Days the location has been open. Defaults to 1000 (Mature site).")

class GranularTimeSeries(BaseModel):
    """Daily, Weekly, and Monthly 12-month projections."""
    daily: List[TimeSeriesPrediction]
    weekly: List[TimeSeriesPrediction]
    monthly: List[TimeSeriesPrediction]

class PlotExportRequest(BaseModel):
    """Request schema for HTML Bokeh plot generation."""
    postcode: str = Field(..., description="The postcode to use for the title")
    dates: List[str] = Field(..., description="X-axis dates/labels")
    sales: List[float] = Field(..., description="Y-axis predicted sales")
    granularity: str = Field("Monthly", description="The current view granularity (Daily, Weekly, Monthly)")
    features: Dict[str, Any] = Field(default_factory=dict, description="Model features")
    display_data: Dict[str, Any] = Field(default_factory=dict, description="Display data (demographics, ethnicity, etc)")

class PredictResponse(BaseModel):
    """Response schema returning the £ sales prediction and the features used."""
    postcode: str
    source: str = Field(..., description="Indicates whether the data came from a 'live_scrape' or 'database_cache'")
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
