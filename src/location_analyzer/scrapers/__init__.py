"""Scraper framework — base class, demographics, CrystalRoof, FreeMapTools, Google Maps."""

from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.scrapers.streetcheck import DemographicsScraper
from location_analyzer.scrapers.crystalroof import CrystalRoofScraper
from location_analyzer.scrapers.freemaptools import RadiusScraper
from location_analyzer.scrapers.google_maps import GoogleMapsScraper

__all__ = [
    "BaseScraper",
    "DemographicsScraper",
    "CrystalRoofScraper",
    "RadiusScraper",
    "GoogleMapsScraper",
]
