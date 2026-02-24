"""
Tests for the JSON file cache manager.
"""

import time

import pytest

from location_analyzer.data.cache import CacheManager


@pytest.fixture
def cache(tmp_path):
    """Create a CacheManager with a temp directory."""
    return CacheManager(cache_dir=str(tmp_path / "cache"), ttl_seconds=60)


class TestCacheBasicOperations:
    """Tests for basic cache get/set/has/invalidate."""

    def test_set_and_get(self, cache):
        """Should store and retrieve data."""
        cache.set("demographics", "SW1A 1AA", {"population": 50000})
        result = cache.get("demographics", "SW1A 1AA")
        assert result == {"population": 50000}

    def test_get_missing(self, cache):
        """Should return None for missing entries."""
        assert cache.get("demographics", "NONEXISTENT") is None

    def test_has_returns_true(self, cache):
        """Should return True for existing entries."""
        cache.set("crystal", "E1 6AN", {"data": True})
        assert cache.has("crystal", "E1 6AN") is True

    def test_has_returns_false(self, cache):
        """Should return False for missing entries."""
        assert cache.has("gmaps", "FAKE") is False

    def test_invalidate_existing(self, cache):
        """Should remove and return True for existing entries."""
        cache.set("demographics", "SW1A 1AA", {"pop": 1000})
        assert cache.invalidate("demographics", "SW1A 1AA") is True
        assert cache.get("demographics", "SW1A 1AA") is None

    def test_invalidate_missing(self, cache):
        """Should return False for non-existent entries."""
        assert cache.invalidate("demographics", "NOPE") is False

    def test_postcode_normalization(self, cache):
        """Should normalize postcodes: spaces → underscores, uppercase."""
        cache.set("demographics", "sw1a 1aa", {"pop": 1})
        result = cache.get("demographics", "SW1A 1AA")
        assert result == {"pop": 1}


class TestCacheTTL:
    """Tests for cache TTL (time-to-live) expiration."""

    def test_expired_entry_returns_none(self, tmp_path):
        """Should return None for expired entries."""
        cache = CacheManager(cache_dir=str(tmp_path / "cache"), ttl_seconds=0)
        cache.set("demographics", "E1 6AN", {"pop": 1})
        # TTL is 0 seconds, so it should expire immediately
        time.sleep(0.1)
        assert cache.get("demographics", "E1 6AN") is None


class TestCacheClear:
    """Tests for clearing cache entries."""

    def test_clear_all(self, cache):
        """Should clear all entries across all categories."""
        cache.set("demographics", "A1 1AA", {"a": 1})
        cache.set("crystal", "B2 2BB", {"b": 2})

        count = cache.clear()
        assert count == 2
        assert cache.get("demographics", "A1 1AA") is None
        assert cache.get("crystal", "B2 2BB") is None

    def test_clear_single_category(self, cache):
        """Should clear only the specified category."""
        cache.set("demographics", "A1 1AA", {"a": 1})
        cache.set("crystal", "B2 2BB", {"b": 2})

        count = cache.clear(category="demographics")
        assert count == 1
        assert cache.get("demographics", "A1 1AA") is None
        assert cache.get("crystal", "B2 2BB") is not None  # untouched


class TestCacheStats:
    """Tests for cache statistics."""

    def test_stats_empty(self, cache):
        """Should return 0 for empty cache."""
        stats = cache.stats()
        assert stats.get("demographics", 0) == 0

    def test_stats_with_entries(self, cache):
        """Should count entries per category."""
        cache.set("demographics", "A1 1AA", {"a": 1})
        cache.set("demographics", "B2 2BB", {"b": 2})
        cache.set("crystal", "C3 3CC", {"c": 3})

        stats = cache.stats()
        assert stats["demographics"] == 2
        assert stats["crystal"] == 1
