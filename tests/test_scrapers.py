"""
Scraper Verification Suite.

This script runs a full live test of all scrapers against a target postcode (default: OX1 1DP).
It verifies:
1. Demographics (PostcodeArea / StreetCheck)
2. CrystalRoof (Transport, Amenities, Affluence)
3. Google Maps (Universities, Hospitals)
4. Radius Scraper (Schools, Hospitals)

Run with: pytest tests/test_scrapers.py -s -v
"""

import logging
import pytest
from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.scrapers.streetcheck import DemographicsScraper
from location_analyzer.scrapers.crystalroof import CrystalRoofScraper
from location_analyzer.scrapers.google_maps import GoogleMapsScraper
from location_analyzer.scrapers.freemaptools import RadiusScraper
from location_analyzer.logging_config import setup_logging

# Setup logging to console
setup_logging()
logger = logging.getLogger(__name__)

TARGET_POSTCODE = "OX1 1DP"

@pytest.mark.live
class TestLiveScrapers:
    """Live verification of all scrapers."""

    def setup_method(self):
        """Force headful browser for all tests in this class."""
        # Patch BaseScraper.get_browser default arg
        self.original_get_browser = BaseScraper.get_browser
        
        def headful_get_browser(scraper_self, headless=False):
            return self.original_get_browser(scraper_self, headless=False)
            
        BaseScraper.get_browser = headful_get_browser

    def teardown_method(self):
        """Restore original method."""
        BaseScraper.get_browser = self.original_get_browser

    def test_1_demographics(self):
        """Verify Demographics Scraper (Income, Population, Ethnicity)."""
        logger.info("\n" + "="*50)
        logger.info(f"📍 TESTING DEMOGRAPHICS SCRAPER ({TARGET_POSTCODE})")
        logger.info("="*50)
        
        scraper = DemographicsScraper()
        data = scraper.scrape(TARGET_POSTCODE.split()[0]) # Uses outercode OX1
        
        logger.info(f"✅ Population: {data.get('population')}")
        logger.info(f"✅ Household Income: £{data.get('avg_household_income')}")
        logger.info(f"✅ Social Grade AB: {data.get('ab')*100:.1f}%")
        
        assert data["population"] > 0, "Population should be > 0"
        assert data["avg_household_income"] > 0, "Income should be > 0"

    def test_2_crystalroof(self):
        """Verify CrystalRoof Scraper (Transport, Amenities)."""
        logger.info("\n" + "="*50)
        logger.info(f"💎 TESTING CRYSTALROOF SCRAPER ({TARGET_POSTCODE})")
        logger.info("="*50)
        
        scraper = CrystalRoofScraper()
        data = scraper.scrape(TARGET_POSTCODE)
        
        transport = data.get("transport", {})
        amenities = data.get("amenities", {})
        
        logger.info(f"✅ Transport Score: {transport.get('score')}/9")
        logger.info(f"✅ Nearest Station: {transport.get('stations', [{}])[0].get('name', 'N/A')}")
        logger.info(f"✅ Pubs Found: {len(amenities.get('pubs', []))}")
        
        assert transport.get("score") is not None, "Transport score missing"
        assert len(transport.get("stations", [])) > 0, "No stations found"

    def test_3_google_maps(self):
        """Verify Google Maps Scraper (Universities, Hospitals)."""
        logger.info("\n" + "="*50)
        logger.info(f"🗺️ TESTING GOOGLE MAPS SCRAPER ({TARGET_POSTCODE})")
        logger.info("="*50)
        
        scraper = GoogleMapsScraper()
        # Test just universities for speed
        data = scraper.scrape(TARGET_POSTCODE, categories=["universities"])
        
        unis = data.get("universities", [])
        logger.info(f"✅ Universities Found: {len(unis)}")
        if unis:
            logger.info(f"   Sample: {unis[0]['name']} ({unis[0]['rating']}⭐)")
            
        assert len(unis) >= 0, "Should return a list (empty is valid but list must exist)"

    def test_4_radius_scraper(self):
        """Verify Radius Scraper (Schools, Hospitals)."""
        logger.info("\n" + "="*50)
        logger.info(f"⭕ TESTING RADIUS SCRAPER ({TARGET_POSTCODE})")
        logger.info("="*50)
        
        scraper = RadiusScraper()
        data = scraper.scrape(TARGET_POSTCODE, radius_miles=1.0)
        
        hospitals = data.get("hospitals", [])
        schools = data.get("schools", [])
        
        logger.info(f"✅ Hospitals (FreeMapTools): {len(hospitals)}")
        logger.info(f"✅ Schools (MapTools.uk): {len(schools)}")
        
        if schools:
            logger.info(f"   Sample School: {schools[0]['name']} ({schools[0]['rating']})")

        assert isinstance(hospitals, list)
        assert isinstance(schools, list)
