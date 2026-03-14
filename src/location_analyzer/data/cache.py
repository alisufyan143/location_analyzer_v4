"""
Thread-safe JSON file cache for scraped data.

Provides a persistent cache that falls back to cached data when scrapers
fail. Data is stored as JSON files in the cache directory, organized
by data type (demographics, crystal, gmaps).
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Any, Optional
from filelock import FileLock

from location_analyzer.config import settings
from location_analyzer.logging_config import get_logger

logger = get_logger(__name__)


class CacheManager:
    """
    Thread-safe file-based JSON cache.

    Organizes cache files by type:
        cache_dir/
            demographics/
                SW1A_1AA.json
            crystal/
                SW1A_1AA.json
            gmaps/
                SW1A_1AA.json
    """

    CATEGORIES = ("demographics", "crystal", "gmaps", "sales")

    def __init__(self, cache_dir: str | None = None, ttl_seconds: int = 86400 * 30):
        """
        Args:
            cache_dir: Override cache directory from settings.
            ttl_seconds: Time-to-live for cached entries. Default 30 days.
        """
        self.cache_dir = Path(cache_dir or settings.paths.cache_dir)
        self.ttl_seconds = ttl_seconds
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create cache subdirectories."""
        for category in self.CATEGORIES:
            (self.cache_dir / category).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_key(key: str) -> str:
        """
        Generate a filesystem-safe filename from the key using MD5.
        This handles special characters (like '|', '=', '/') safely.
        """
        # Normalize key before hashing: uppercase + strip so "SW1A 1AA" and
        # "sw1a 1aa" always map to the same cache file.
        return hashlib.md5(key.strip().upper().encode("utf-8")).hexdigest()

    def _path_for(self, category: str, key: str) -> Path:
        """Get the file path for a cache entry."""
        return self.cache_dir / category / f"{self._safe_key(key)}.json"

    def _lock_for(self, path: Path) -> FileLock:
        """Get a file lock for thread-safe access."""
        return FileLock(str(path) + ".lock", timeout=5)

    def get(self, category: str, postcode: str) -> Optional[dict[str, Any]]:
        """
        Retrieve cached data.

        Args:
            category: One of 'demographics', 'crystal', 'gmaps', 'sales'.
            postcode: UK postcode.

        Returns:
            Cached data dict, or None if not found or expired.
        """
        path = self._path_for(category, postcode)
        if not path.exists():
            return None

        lock = self._lock_for(path)
        try:
            with lock:
                data = json.loads(path.read_text(encoding="utf-8"))
                # Check TTL
                cached_at = data.get("_cached_at", 0)
                if time.time() - cached_at > self.ttl_seconds:
                    logger.debug("Cache expired for %s/%s", category, postcode)
                    return None
                return data.get("payload")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache read error for %s/%s: %s", category, postcode, e)
            return None

    def set(self, category: str, postcode: str, data: dict[str, Any]) -> None:
        """
        Store data in cache.

        Args:
            category: One of 'demographics', 'crystal', 'gmaps', 'sales'.
            postcode: UK postcode.
            data: The data dict to cache.
        """
        path = self._path_for(category, postcode)
        lock = self._lock_for(path)

        envelope = {
            "_cached_at": time.time(),
            "_postcode": postcode,
            "payload": data,
        }

        try:
            with lock:
                path.write_text(
                    json.dumps(envelope, indent=2, default=str),
                    encoding="utf-8",
                )
            logger.debug("Cached %s data for %s", category, postcode)
        except OSError as e:
            logger.error("Cache write error for %s/%s: %s", category, postcode, e)

    def has(self, category: str, postcode: str) -> bool:
        """Check if valid (non-expired) cache exists."""
        return self.get(category, postcode) is not None

    def invalidate(self, category: str, postcode: str) -> bool:
        """
        Remove a specific cache entry.

        Returns:
            True if the entry was removed, False if it didn't exist.
        """
        path = self._path_for(category, postcode)
        if path.exists():
            path.unlink()
            logger.debug("Invalidated cache for %s/%s", category, postcode)
            return True
        return False

    def clear(self, category: str | None = None) -> int:
        """
        Clear all cache entries, optionally for a specific category.

        Returns:
            Number of entries removed.
        """
        count = 0
        categories = [category] if category else self.CATEGORIES
        for cat in categories:
            cat_dir = self.cache_dir / cat
            if cat_dir.exists():
                for f in cat_dir.glob("*.json"):
                    f.unlink()
                    count += 1
                # Clean up lock files too
                for f in cat_dir.glob("*.lock"):
                    f.unlink()
        logger.info("Cleared %d cache entries", count)
        return count

    def stats(self) -> dict[str, int]:
        """Return cache statistics: entry count per category."""
        return {
            cat: len(list((self.cache_dir / cat).glob("*.json")))
            for cat in self.CATEGORIES
            if (self.cache_dir / cat).exists()
        }
