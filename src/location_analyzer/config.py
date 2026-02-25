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
    doogal_requests_timeout_sec: int = 20
    doogal_wait_until_modes: list[str] = ["domcontentloaded", "load"]

    # Doogal execution policy (L1 -> L5) bounded by a hard deadline.
    # This keeps the exec-facing UX predictable while still allowing fallback.
    doogal_total_budget_sec: int = 75
    doogal_l1_max_attempts: int = 2
    doogal_l1_attempt_timeout_sec: int = 12
    doogal_l1_retry_delay_sec: float = 0.6
    doogal_l5_max_attempts: int = 1
    doogal_l5_retry_delay_sec: float = 1.5

    # Reliability SLOs and policy controls used by the intelligent Doogal selector.
    doogal_slo_success_rate: float = 0.98
    doogal_slo_timeout_rate: float = 0.015
    doogal_slo_blocked_rate: float = 0.005
    doogal_slo_p95_latency_sec: float = 35.0
    doogal_selector_window: int = 80
    doogal_selector_min_samples: int = 10
    doogal_cb_fail_threshold: int = 5
    doogal_cb_cooldown_sec: int = 300
    doogal_retry_base_sec: float = 2.0
    doogal_retry_max_sec: float = 20.0

    model_config = SettingsConfigDict(env_prefix="SCRAPER_")

    @field_validator("doogal_proxies", mode="before")
    @classmethod
    def parse_doogal_proxies(cls, v: str | list[str] | None) -> list[str] | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("doogal_wait_until_modes", mode="before")
    @classmethod
    def parse_doogal_wait_modes(cls, v: str | list[str] | None) -> list[str]:
        if v is None or v == "":
            return ["domcontentloaded", "load"]
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        return [str(m).strip() for m in v if str(m).strip()]


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
