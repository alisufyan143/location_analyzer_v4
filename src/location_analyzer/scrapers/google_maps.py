"""
Google Maps Scraper - Extracts proximity data for institutions and businesses.
Source: google.com/maps
"""

import re
import time
import random
from typing import Any, List, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import ScraperParsingError, ScraperError

logger = get_logger(__name__)

class GoogleMapsScraper(BaseScraper):
    """
    Scraper for Google Maps to find proximity venues (Universities, Hospitals, etc.).
    """
    CACHE_CATEGORY = "google_maps"

    def scrape(self, postcode: str, categories: Optional[List[str]] = None) -> dict[str, Any]:
        """
        Search for specific categories near a postcode.
        
        Args:
            postcode: UK Postcode.
            categories: List of search terms (e.g. ['universities', 'hospitals']).
        """
        if not categories:
            categories = ["universities", "hospitals", "major businesses"]

        results = {}
        logger.info("Searching Google Maps for %s near %s", categories, postcode)

        with sync_playwright() as p:
            # Use stealth-like headers and a real browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            for category in categories:
                try:
                    category_data = self._scrape_category(page, postcode, category)
                    results[category] = category_data
                except Exception as e:
                    logger.error("Failed to scrape category %s: %s", category, e)
                    results[category] = []

            browser.close()

        return results

    def _scrape_category(self, page, postcode: str, category: str) -> List[dict[str, Any]]:
        """Scrape a single category search."""
        query = f"{category} near {postcode}"
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}/"
        
        logger.debug("Navigating to %s", url)
        # Using 'load' instead of 'networkidle' as Google Maps has constant background traffic
        page.goto(url, wait_until="load", timeout=60000)
        
        # Explicitly wait for the results feed or the "No results found" message
        try:
            # .hfpxzc is a single result anchor. 
            # We can also look for the role="feed" container.
            page.wait_for_selector(".hfpxzc", timeout=15000)
            # Give it a tiny bit more time to settle
            time.sleep(2)
        except Exception:
            logger.warning("No results selector .hfpxzc found for %s near %s", category, postcode)
            # Check if there's a "No results found" text
            if "No results found" in page.content():
                 return []
            # Otherwise return what we have (might be limited)

        # Optional: Scroll a bit to load more if needed, but for 'nail in coffin' 
        # the top 5-10 are usually enough.
        
        soup = BeautifulSoup(page.content(), "html.parser")
        items = soup.find_all("a", class_="hfpxzc")
        
        places = []
        for item in items[:10]: # Limit to top 10
            name = item.get("aria-label", "Unknown")
            
            # Navigate to the card's parent for more details
            # Google Maps structure is messy, often the rating is in a sibling container
            card = item.parent
            rating = 0.0
            review_count = 0
            
            # Look for ratings (e.g., "4.5 (123)")
            rating_text = card.get_text()
            rating_match = re.search(r"(\d\.\d)\s*\((\d,?\d*)\)", rating_text)
            if rating_match:
                rating = float(rating_match.group(1))
                review_count = int(rating_match.group(2).replace(",", ""))

            places.append({
                "name": name,
                "rating": rating,
                "reviews": review_count,
                "category": category
            })
            
        return places
