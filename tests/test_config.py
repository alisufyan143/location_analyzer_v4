"""
Tests for configuration management.

Validates that settings load correctly from environment variables
and that validation rules work as expected.
"""

import os
import pytest

from location_analyzer.config import (
    Settings,
    DatabaseSettings,
    APISettings,
    ScraperSettings,
    MLSettings,
    PathSettings,
    LoggingSettings,
)


class TestDatabaseSettings:
    """Tests for database configuration."""

    def test_default_sqlite(self):
        """Default database should be SQLite for development."""
        settings = DatabaseSettings()
        assert "sqlite" in settings.url

    def test_custom_url(self, monkeypatch):
        """Database URL should be configurable via env var."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
        settings = DatabaseSettings()
        assert settings.url == "postgresql://user:pass@localhost/testdb"


class TestAPISettings:
    """Tests for API configuration."""

    def test_defaults(self):
        """Default API settings should be sensible for development."""
        settings = APISettings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.reload is True
        assert "*" in settings.cors_origins

    def test_custom_port(self, monkeypatch):
        """Port should be configurable."""
        monkeypatch.setenv("API_PORT", "9000")
        settings = APISettings()
        assert settings.port == 9000


class TestScraperSettings:
    """Tests for scraper configuration."""

    def test_defaults(self):
        """Default scraper settings should have reasonable delays."""
        settings = ScraperSettings()
        assert settings.min_delay == 2.0
        assert settings.max_delay == 8.0
        assert settings.max_retries == 3
        assert settings.headless is True
        assert settings.proxies is None

    def test_parse_proxies_string(self, monkeypatch):
        """Proxies should be parseable from comma-separated string."""
        monkeypatch.setenv("SCRAPER_PROXIES", "http://proxy1:8080, http://proxy2:8080")
        settings = ScraperSettings()
        assert settings.proxies == ["http://proxy1:8080", "http://proxy2:8080"]

    def test_parse_proxies_empty(self, monkeypatch):
        """Empty proxies string should result in None."""
        monkeypatch.setenv("SCRAPER_PROXIES", "")
        settings = ScraperSettings()
        assert settings.proxies is None

    def test_min_delay_configurable(self, monkeypatch):
        """Delays should be configurable."""
        monkeypatch.setenv("SCRAPER_MIN_DELAY", "5.0")
        monkeypatch.setenv("SCRAPER_MAX_DELAY", "15.0")
        settings = ScraperSettings()
        assert settings.min_delay == 5.0
        assert settings.max_delay == 15.0


class TestMLSettings:
    """Tests for ML configuration."""

    def test_defaults(self):
        """Default ML settings."""
        settings = MLSettings()
        assert settings.models_dir == "models"
        assert settings.default_metric == "rmse"


class TestPathSettings:
    """Tests for path configuration."""

    def test_defaults(self):
        """Default paths should be set."""
        settings = PathSettings()
        assert settings.data_dir == "data"
        assert settings.cache_dir == "data/cache"

    def test_ensure_dirs(self, tmp_path, monkeypatch):
        """ensure_dirs should create all configured directories."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "test_data"))
        monkeypatch.setenv("DEMOGRAPHIC_DATA_DIR", str(tmp_path / "test_demo"))
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "test_output"))
        monkeypatch.setenv("CACHE_DIR", str(tmp_path / "test_cache"))
        monkeypatch.setenv("PLOTS_DIR", str(tmp_path / "test_plots"))
        settings = PathSettings()
        settings.ensure_dirs()
        assert (tmp_path / "test_data").exists()
        assert (tmp_path / "test_demo").exists()
        assert (tmp_path / "test_output").exists()
        assert (tmp_path / "test_cache").exists()
        assert (tmp_path / "test_plots").exists()


class TestLoggingSettings:
    """Tests for logging configuration."""

    def test_defaults(self):
        """Default logging settings."""
        settings = LoggingSettings()
        assert settings.level == "INFO"
        assert "location_analyzer" in settings.file


class TestMainSettings:
    """Tests for the aggregated Settings object."""

    def test_settings_loads(self):
        """Main settings object should load without errors."""
        settings = Settings()
        assert settings.database is not None
        assert settings.api is not None
        assert settings.scraper is not None
        assert settings.ml is not None
        assert settings.paths is not None
        assert settings.logging is not None

    def test_settings_has_all_subsettings(self):
        """Settings should aggregate all sub-settings."""
        settings = Settings()
        subsettings = ["database", "api", "scraper", "ml", "paths", "ngrok", "logging"]
        for name in subsettings:
            assert hasattr(settings, name), f"Missing sub-setting: {name}"
