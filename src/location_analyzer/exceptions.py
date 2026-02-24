"""
Custom exception hierarchy for the Location Analyzer.

Provides specific exception types for each subsystem,
enabling targeted error handling throughout the application.
"""


class LocationAnalyzerError(Exception):
    """Base exception for all Location Analyzer errors."""

    def __init__(self, message: str = "", details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# --- Scraper Exceptions ---


class ScraperError(LocationAnalyzerError):
    """Base exception for scraping errors."""
    pass


class ScraperBlockedError(ScraperError):
    """Raised when the scraper is detected/blocked by the target website."""
    pass


class ScraperTimeoutError(ScraperError):
    """Raised when a scraping operation times out."""
    pass


class ScraperParsingError(ScraperError):
    """Raised when scraped HTML cannot be parsed (likely a layout change)."""
    pass


class ScraperFallbackExhaustedError(ScraperError):
    """Raised when all fallback sources have been tried and failed."""
    pass


# --- Database Exceptions ---


class DatabaseError(LocationAnalyzerError):
    """Base exception for database errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when the database connection fails."""
    pass


class PostcodeNotFoundError(DatabaseError):
    """Raised when a postcode is not found in the database or cache."""

    def __init__(self, postcode: str):
        super().__init__(
            message=f"Postcode '{postcode}' not found",
            details={"postcode": postcode},
        )


# --- ML Exceptions ---


class PredictionError(LocationAnalyzerError):
    """Base exception for prediction/ML errors."""
    pass


class ModelNotFoundError(PredictionError):
    """Raised when no trained model is available."""
    pass


class TrainingDataError(PredictionError):
    """Raised when training data is missing, invalid, or insufficient."""
    pass


class FeatureEngineeringError(PredictionError):
    """Raised when feature engineering fails (missing columns, bad types, etc.)."""
    pass


# --- Validation Exceptions ---


class ValidationError(LocationAnalyzerError):
    """Base exception for input validation errors."""
    pass


class InvalidPostcodeError(ValidationError):
    """Raised when a postcode format is invalid."""

    def __init__(self, postcode: str):
        super().__init__(
            message=f"Invalid UK postcode format: '{postcode}'",
            details={"postcode": postcode},
        )
