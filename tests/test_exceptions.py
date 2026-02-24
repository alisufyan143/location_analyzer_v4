"""
Tests for the exception hierarchy.

Validates that all exception classes are properly structured
and can carry relevant context information.
"""

import pytest

from location_analyzer.exceptions import (
    LocationAnalyzerError,
    ScraperError,
    ScraperBlockedError,
    ScraperTimeoutError,
    ScraperParsingError,
    ScraperFallbackExhaustedError,
    DatabaseError,
    DatabaseConnectionError,
    PostcodeNotFoundError,
    PredictionError,
    ModelNotFoundError,
    TrainingDataError,
    FeatureEngineeringError,
    ValidationError,
    InvalidPostcodeError,
)


class TestExceptionHierarchy:
    """Tests that the exception hierarchy is correct."""

    def test_all_inherit_from_base(self):
        """All custom exceptions should inherit from LocationAnalyzerError."""
        exception_classes = [
            ScraperError,
            ScraperBlockedError,
            ScraperTimeoutError,
            ScraperParsingError,
            ScraperFallbackExhaustedError,
            DatabaseError,
            DatabaseConnectionError,
            PostcodeNotFoundError,
            PredictionError,
            ModelNotFoundError,
            TrainingDataError,
            FeatureEngineeringError,
            ValidationError,
            InvalidPostcodeError,
        ]
        for exc_class in exception_classes:
            assert issubclass(exc_class, LocationAnalyzerError), (
                f"{exc_class.__name__} should inherit from LocationAnalyzerError"
            )

    def test_scraper_hierarchy(self):
        """Scraper exceptions should inherit from ScraperError."""
        assert issubclass(ScraperBlockedError, ScraperError)
        assert issubclass(ScraperTimeoutError, ScraperError)
        assert issubclass(ScraperParsingError, ScraperError)
        assert issubclass(ScraperFallbackExhaustedError, ScraperError)

    def test_database_hierarchy(self):
        """Database exceptions should inherit from DatabaseError."""
        assert issubclass(DatabaseConnectionError, DatabaseError)
        assert issubclass(PostcodeNotFoundError, DatabaseError)

    def test_prediction_hierarchy(self):
        """ML exceptions should inherit from PredictionError."""
        assert issubclass(ModelNotFoundError, PredictionError)
        assert issubclass(TrainingDataError, PredictionError)
        assert issubclass(FeatureEngineeringError, PredictionError)

    def test_validation_hierarchy(self):
        """Validation exceptions should inherit from ValidationError."""
        assert issubclass(InvalidPostcodeError, ValidationError)


class TestExceptionDetails:
    """Tests that exceptions carry proper context."""

    def test_base_exception_with_message(self):
        """Base exception should accept a message."""
        exc = LocationAnalyzerError("Something went wrong")
        assert str(exc) == "Something went wrong"
        assert exc.message == "Something went wrong"

    def test_base_exception_with_details(self):
        """Base exception should accept a details dict."""
        exc = LocationAnalyzerError("Error", details={"key": "value"})
        assert exc.details == {"key": "value"}

    def test_postcode_not_found(self):
        """PostcodeNotFoundError should format the postcode in the message."""
        exc = PostcodeNotFoundError("W13 0SA")
        assert "W13 0SA" in str(exc)
        assert exc.details["postcode"] == "W13 0SA"

    def test_invalid_postcode(self):
        """InvalidPostcodeError should format the postcode in the message."""
        exc = InvalidPostcodeError("INVALID")
        assert "INVALID" in str(exc)
        assert exc.details["postcode"] == "INVALID"

    def test_catch_by_category(self):
        """Should be catchable by category (e.g., catch all scraper errors)."""
        with pytest.raises(ScraperError):
            raise ScraperBlockedError("Blocked by Cloudflare")

        with pytest.raises(DatabaseError):
            raise PostcodeNotFoundError("AB1 2CD")

        with pytest.raises(PredictionError):
            raise ModelNotFoundError("No trained model")

    def test_catch_by_base(self):
        """All errors should be catchable by LocationAnalyzerError."""
        errors = [
            ScraperBlockedError("blocked"),
            PostcodeNotFoundError("AB1 2CD"),
            ModelNotFoundError("no model"),
            InvalidPostcodeError("bad"),
        ]
        for error in errors:
            with pytest.raises(LocationAnalyzerError):
                raise error
