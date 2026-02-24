"""
Application configuration using Pydantic Settings.

All settings are loaded from environment variables or .env file.
No hardcoded secrets or paths — everything is configurable.
"""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env so SCRAPER_DOOGAL_PROXIES etc. are available before Settings() is built.
# Prefer project root (parent of src/), then current working directory.
_env_dir = Path(__file__).resolve().parents[2]
load_dotenv(_env_dir / ".env")
load_dotenv()


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    
    url: str = "sqlite:///./data/location_analyzer.db"

    model_config = SettingsConfigDict(env_prefix="DATABASE_")


class APISettings(BaseSettings):
    """FastAPI server settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_prefix="API_")


class ScraperSettings(BaseSettings):
    """Web scraping configuration."""

    min_delay: float = 2.0
    max_delay: float = 8.0
    max_retries: int = 3
    timeout: int = 30
    headless: bool = True
    nomis_api_uid: Optional[str] = None
    # Doogal-only rotating proxy (comma-separated). Not used by other scrapers.
    doogal_proxies: Optional[list[str]] = None
    # Doogal tab timing (from timing run with proxy). Tune via SCRAPER_DOOGAL_* env vars.
    doogal_goto_timeout_ms: int = 45_000   # max wait for page load (domcontentloaded)
    doogal_wait_after_load_ms: int = 8_000 # wait after load for income to render (max ~8s observed)
    doogal_retries: int = 2                 # retries on failure or missing income
    doogal_retry_delay_sec: int = 10        # seconds to wait before next retry (avoid rate limits)

    model_config = SettingsConfigDict(env_prefix="SCRAPER_")

    @field_validator("doogal_proxies", mode="before")
    @classmethod
    def parse_doogal_proxies(cls, v: str | list[str] | None) -> list[str] | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v


class MLSettings(BaseSettings):
    """Machine learning configuration."""

    models_dir: str = "models"
    default_metric: str = "rmse"

    model_config = SettingsConfigDict(env_prefix="ML_")


class PathSettings(BaseSettings):
    """File path configuration."""

    data_dir: str = "data"
    demographic_data_dir: str = "data/demographic_data"
    output_dir: str = "data/output"
    cache_dir: str = "data/cache"
    plots_dir: str = "data/plots"

    model_config = SettingsConfigDict(env_prefix="")

    def ensure_dirs(self) -> None:
        """Create all configured directories if they don't exist."""
        for field_name in self.__class__.model_fields:
            path = Path(getattr(self, field_name))
            path.mkdir(parents=True, exist_ok=True)


class NgrokSettings(BaseSettings):
    """ngrok tunnel settings for development."""

    auth_token: Optional[str] = None
    domain: Optional[str] = None

    model_config = SettingsConfigDict(env_prefix="NGROK_")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "logs/location_analyzer.log"

    model_config = SettingsConfigDict(env_prefix="LOG_")


class Settings(BaseSettings):
    """Main application settings — aggregates all sub-settings."""

    database: DatabaseSettings = DatabaseSettings()
    api: APISettings = APISettings()
    scraper: ScraperSettings = ScraperSettings()
    ml: MLSettings = MLSettings()
    paths: PathSettings = PathSettings()
    ngrok: NgrokSettings = NgrokSettings()
    logging: LoggingSettings = LoggingSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def setup(self) -> None:
        """Initialize application: create directories, configure logging."""
        self.paths.ensure_dirs()
        # Ensure log directory exists
        log_dir = Path(self.logging.file).parent
        log_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance — import this in other modules
settings = Settings()
