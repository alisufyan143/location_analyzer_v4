"""
Radius Scraper - Fetches count of institutions within a radius.
Sources: 
- Hospitals: freemaptools.com
- Schools: maptools.uk

This unified scraper uses different strategies for each source but exposes
a single `scrape(postcode, categories)` interface.
"""

import time
import urllib.parse
from typing import Any, List
from bs4 import BeautifulSoup

from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import ScraperError

logger = get_logger(__name__)

class RadiusScraper(BaseScraper):
    """
    Scraper for "within radius" tools.
    
    Supported Categories:
    - hospitals: Uses FreeMapTools (radius=2 miles default)
    - schools: Uses MapTools.uk (radius=1 mile default)
    """
    
    CACHE_CATEGORY = "radius_data"
    
    # Source URLs
    URL_HOSPITALS = "https://www.freemaptools.com/find-uk-hospitals-inside-radius.htm"
    URL_SCHOOLS = "https://www.maptools.uk/tools/school-finder/"

    def scrape(self, postcode: str, radius_miles: float = 1.0) -> dict[str, Any]:
        """
        Scrape all registered radius categories for the postcode.
        
        Args:
            postcode: Target postcode (e.g. "UB5 5AF")
            radius_miles: Search radius (default 1.0 for consistency, though sources vary)
            
        Returns:
            Dict with keys 'hospitals', 'schools', each containing a list of found items.
        """
        postcode = postcode.strip().upper()
        results = {
            "hospitals": [],
            "schools": []
        }

        # Use a single browser session for efficiency
        # We need a headless browser for ID selection and form submission
        browser = self.get_browser(headless=True)
        
        try:
            # 1. Hospitals (FreeMapTools)
            try:
                # Hospitals usually need a slightly larger radius to be useful
                results["hospitals"] = self._scrape_hospitals(browser, postcode, radius=2.0)
            except Exception as e:
                logger.error("Failed to scrape hospitals for %s: %s", postcode, e)

            # 2. Schools (MapTools.uk)
            try:
                results["schools"] = self._scrape_schools(browser, postcode, radius=radius_miles)
            except Exception as e:
                logger.error("Failed to scrape schools for %s: %s", postcode, e)
                
        finally:
            # Browser is managed by get_browser cache in BaseScraper but we can close page
            pass

        return results

    def _scrape_hospitals(self, browser, postcode: str, radius: float) -> List[str]:
        """
        Scrape FreeMapTools for hospitals.
        Returns a list of hospital names string.
        """
        logger.info("Scraping hospitals near %s (radius=%.1f miles)", postcode, radius)
        browser.get(self.URL_HOSPITALS)
        
        # Wait for map/tools to load
        time.sleep(2)
        
        # Inject values directly to avoid overlay interceptions
        browser.execute_script(f"document.getElementById('tb_radius_miles').value = '{radius}';")
        browser.execute_script(f"document.getElementById('locationSearchTextBox').value = '{postcode}';")
        
        # Click search
        browser.execute_script("document.getElementById('locationSearchButton').click();")
        
        # Poll for results in #tb_output
        for _ in range(30): # 60 seconds max
            time.sleep(2)
            val = browser.execute_script("return document.getElementById('tb_output').value;")
            if val and len(val) > 5:
                # Comma separated list
                items = [x.strip() for x in val.split(",") if x.strip()]
                return [{"name": item, "distance": "N/A"} for item in items]
                
        logger.warning("Timeout waiting for hospital results")
        return []

    def _scrape_schools(self, browser, postcode: str, radius: float) -> List[dict]:
        """
        Scrape MapTools.uk for schools.
        Returns list of dicts: {name, distance, rating, phase}
        """
        logger.info("Scraping schools near %s (radius=%.1f miles)", postcode, radius)
        browser.get(self.URL_SCHOOLS)
        
        # Wait for form
        time.sleep(2)
        
        # Set Postcode
        browser.execute_script(f"document.getElementById('postcodeInput').value = '{postcode}';")
        
        # Set Radius (Approximate selection)
        # Options are usually: 1 mile, 3 miles, 5 miles. We try to select the closest.
        # This script iterates options to find "1 mile" or closest match
        browser.execute_script("""
            const sel = document.getElementById('radiusSelect');
            for(let i=0; i<sel.options.length; i++) {
                if(sel.options[i].text.includes('1 mile')) {
                    sel.selectedIndex = i;
                    break;
                }
            }
        """)
        
        # Click Search
        browser.execute_script("document.getElementById('btnSearch').click();")
        
        # Wait for #resultsList to populate
        # We look for .school-card class
        schools = []
        for _ in range(15): # 30 seconds max
            time.sleep(2)
            # Check if results exist
            count = browser.execute_script("return document.querySelectorAll('.school-card').length;")
            if count > 0:
                break
        
        # Parse content
        content = browser.page_source
        soup = BeautifulSoup(content, "html.parser")
        
        cards = soup.select(".school-card")
        for card in cards:
            name_el = card.select_one(".school-name")
            dist_el = card.select_one(".school-distance-badge")
            
            # Meta badges (Phase, Rating, etc are often in .school-badge)
            badges = [b.get_text(strip=True) for b in card.select(".school-badge")]
            
            # Simple heuristics for rating/phase from badges
            rating = "Unknown"
            phase = "Unknown"
            
            for b in badges:
                if b in ["Outstanding", "Good", "Requires Improvement", "Inadequate"]:
                    rating = b
                elif b in ["Primary", "Secondary", "16 plus", "Nursery"]:
                    phase = b

            if name_el:
                schools.append({
                    "name": name_el.get_text(strip=True),
                    "distance": dist_el.get_text(strip=True) if dist_el else "N/A",
                    "rating": rating,
                    "phase": phase
                })
                
        return schools
