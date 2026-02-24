"""
Base scraper with retry logic, rate limiting, browser management, and fallback chain.

All scrapers inherit from BaseScraper and get:
- Automatic retry with exponential backoff
- Random delays between requests (anti-detection)
- User-Agent rotation
- Proxy support
- Browser lifecycle management (Selenium + undetected-chromedriver)
- Cache integration (fallback to cached data on failure)
- Structured logging
"""

import abc
import random
import time
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from location_analyzer.config import settings
from location_analyzer.data.cache import CacheManager
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import (
    ScraperError,
    ScraperTimeoutError,
    ScraperBlockedError,
    ScraperParsingError,
)

logger = get_logger(__name__)


class BaseScraper(abc.ABC):
    """
    Abstract base class for all scrapers.

    Provides:
        - retry_request(): HTTP requests with retry + backoff
        - get_soup(): Parse HTML via requests (lightweight, no browser)
        - get_browser(): Selenium browser for JS-heavy pages
        - throttle(): Random delay between requests
        - with_fallback(): Try scrape → fallback to cache on failure

    Subclasses must implement:
        - scrape(postcode) → dict: The actual scraping logic
        - CACHE_CATEGORY: str: Cache category name (e.g., 'demographics')
    """

    CACHE_CATEGORY: str = ""  # Override in subclasses
    MAX_RETRIES: int = 3
    BACKOFF_BASE: float = 2.0  # Exponential backoff base (seconds)

    def __init__(self):
        self._ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        self._session: Optional[requests.Session] = None
        self._browser = None
        self._cache = CacheManager()

    # ─── Abstract Interface ─────────────────────────────────

    @abc.abstractmethod
    def scrape(self, postcode: str) -> dict[str, Any]:
        """
        Scrape data for a given postcode.

        Args:
            postcode: UK postcode (e.g., 'SW1A 1AA').

        Returns:
            Dict of scraped data.

        Raises:
            ScraperError: If scraping fails after all retries.
        """
        ...

    # ─── Fallback Chain ─────────────────────────────────────

    def scrape_with_fallback(self, postcode: str, **kwargs) -> dict[str, Any]:
        """
        Try scraping, fall back to cache on failure.

        Chain: Live scrape → Cached data → Raise error

        When using arguments (like radius_miles), the cache key incorporates them
        to ensure uniqueness.
        """
        # Create a unique cache key including kwargs if present
        cache_key = postcode
        if kwargs:
            # Sort kwargs for deterministic key (e.g. "SW1A 1AA|radius_miles=2.0")
            arg_str = "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = f"{postcode}|{arg_str}"

        try:
            data = self.scrape(postcode, **kwargs)
            # Cache successful result
            if self.CACHE_CATEGORY and data:
                self._cache.set(self.CACHE_CATEGORY, cache_key, data)
            return data
        except ScraperError as e:
            logger.warning("Scrape failed for %s, trying cache: %s", postcode, e)
            cached = self._cache.get(self.CACHE_CATEGORY, cache_key)
            if cached:
                logger.info("Using cached data for %s", cache_key)
                return cached
            raise

    # ─── HTTP Requests ──────────────────────────────────────

    @property
    def session(self) -> requests.Session:
        """Lazy-init a requests session with rotating headers."""
        if self._session is None:
            self._session = requests.Session()
            self._update_session_headers()
        return self._session

    def _update_session_headers(self) -> None:
        """Rotate User-Agent and set realistic browser headers."""
        self.session.headers.update({
            "User-Agent": self._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
        })
        # Apply proxy if configured
        if settings.scraper.proxies:
            proxy = random.choice(settings.scraper.proxies)
            self.session.proxies = {"http": proxy, "https": proxy}

    def retry_request(
        self,
        url: str,
        method: str = "GET",
        max_retries: int | None = None,
        **kwargs,
    ) -> requests.Response:
        """
        Make an HTTP request with retry + exponential backoff.

        Args:
            url: Target URL.
            method: HTTP method.
            max_retries: Override default retry count.
            **kwargs: Passed to requests.Session.request().

        Returns:
            Response object.

        Raises:
            ScraperTimeoutError: If all retries exhausted.
            ScraperBlockedError: If we receive a 403/429.
        """
        retries = max_retries or self.MAX_RETRIES
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                self._update_session_headers()  # Rotate UA each attempt
                self.throttle()

                response = self.session.request(method, url, timeout=30, **kwargs)

                if response.status_code == 200:
                    return response
                elif response.status_code in (403, 429):
                    raise ScraperBlockedError(
                        message=f"Blocked by {url} (HTTP {response.status_code})",
                        details={"url": url, "status": response.status_code},
                    )
                else:
                    response.raise_for_status()

            except ScraperBlockedError:
                raise  # Don't retry on blocks
            except Exception as e:
                last_error = e
                wait = self.BACKOFF_BASE ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Request attempt %d/%d failed for %s: %s — retrying in %.1fs",
                    attempt, retries, url, e, wait,
                )
                time.sleep(wait)

        raise ScraperTimeoutError(
            message=f"All {retries} attempts failed for {url}",
            details={"url": url, "last_error": str(last_error)},
        )

    def get_soup(self, url: str, **kwargs) -> BeautifulSoup:
        """
        Fetch a URL and return parsed BeautifulSoup.

        Args:
            url: Target URL.
            **kwargs: Passed to retry_request().

        Returns:
            BeautifulSoup object.
        """
        response = self.retry_request(url, **kwargs)
        return BeautifulSoup(response.text, "html.parser")

    # ─── Browser Management (Selenium) ──────────────────────

    def get_browser(self, headless: bool = True):
        """
        Get or create a Selenium browser (undetected-chromedriver).

        Args:
            headless: Run browser without visible window.

        Returns:
            WebDriver instance.
        """
        if self._browser is not None:
            return self._browser

        try:
            import undetected_chromedriver as uc

            options = uc.ChromeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument(f"--user-agent={self._ua.random}")

            # Proxy support
            if settings.scraper.proxies:
                proxy = random.choice(settings.scraper.proxies)
                options.add_argument(f"--proxy-server={proxy}")

            # Auto-detect installed Chrome version to prevent mismatch
            chrome_version = self._detect_chrome_version()
            logger.info("Detected Chrome version: %s", chrome_version or "auto")

            self._browser = uc.Chrome(options=options, version_main=chrome_version)
            self._browser.set_page_load_timeout(60)
            logger.info("Browser session started")
            return self._browser

        except Exception as e:
            raise ScraperError(
                message=f"Failed to start browser: {e}",
                details={"headless": headless},
            ) from e

    @staticmethod
    def _detect_chrome_version() -> int | None:
        """
        Detect installed Chrome major version.

        Checks Windows registry first, then falls back to command line.
        Returns the major version number (e.g., 144) or None.
        """
        import platform
        import subprocess

        try:
            if platform.system() == "Windows":
                # Try Windows registry
                import winreg
                reg_path = r"SOFTWARE\Google\Chrome\BLBeacon"
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
                    version, _ = winreg.QueryValueEx(key, "version")
                    winreg.CloseKey(key)
                    major = int(version.split(".")[0])
                    return major
                except (WindowsError, ValueError):
                    pass

            # Fallback: try running chrome --version
            result = subprocess.run(
                ["google-chrome", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                import re
                match = re.search(r"(\d+)\.", result.stdout)
                if match:
                    return int(match.group(1))

        except Exception:
            pass

        return None  # Let undetected-chromedriver figure it out

    def close_browser(self) -> None:
        """Close the browser if open."""
        if self._browser is not None:
            try:
                self._browser.quit()
            except Exception:
                pass
            self._browser = None
            logger.info("Browser session closed")

    # ─── Rate Limiting ──────────────────────────────────────

    def throttle(self) -> None:
        """Random delay between requests (anti-detection)."""
        delay = random.uniform(settings.scraper.min_delay, settings.scraper.max_delay)
        logger.debug("Throttling %.1fs", delay)
        time.sleep(delay)

    # ─── Utility ────────────────────────────────────────────

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean scraped text: strip whitespace, normalize spaces."""
        return " ".join(text.split()).strip()

    @staticmethod
    def safe_float(value: str, default: float = 0.0) -> float:
        """Safely parse a string to float, stripping currency/percent symbols."""
        try:
            cleaned = value.replace(",", "").replace("£", "").replace("%", "").strip()
            return float(cleaned)
        except (ValueError, AttributeError):
            return default

    @staticmethod
    def safe_int(value: str, default: int = 0) -> int:
        """Safely parse a string to int."""
        try:
            cleaned = value.replace(",", "").strip()
            return int(float(cleaned))
        except (ValueError, AttributeError):
            return default

    # ─── Context Manager ────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_browser()
        if self._session:
            self._session.close()
        return False
