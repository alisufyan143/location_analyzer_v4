"""
CrystalRoof Scraper - Fetches transport, amenities, affluence, and demographics data.
Source: crystalroof.co.uk
URL Pattern: https://crystalroof.co.uk/report/postcode/{postcode}/{section}

This scraper provides high-resolution data including transport scores, exact distance-to-station,
amenity counts (pubs/restaurants), and household income statistics.
"""

import random
import time
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import ScraperParsingError, ScraperError

logger = get_logger(__name__)

# ─── Constants ──────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_DELAY_SECS = 5
PAGE_TIMEOUT_MS = 30000

class CrystalRoofScraper(BaseScraper):
    """
    Scraper for CrystalRoof.co.uk.
    
    Data collected across sub-pages:
    - /transport: Accessibility score, station names, distances, and lines.
    - /amenities: Pubs, restaurants, and supermarkets (names + distances).
    - /affluence: Household income and affluence rating.
    - /affluence?tab=occupation: Socio-economic breakdown (NS-SEC).
    - /demographics: Ethnicity validation.
    """

    CACHE_CATEGORY = "crystal"
    BASE_URL = "https://crystalroof.co.uk/report/postcode"

    def scrape(self, postcode: str) -> dict[str, Any]:
        """
        Scrape all CrystalRoof sections for a postcode.
        """
        postcode_clean = postcode.strip().upper().replace(" ", "")
        
        logger.info("Scraping CrystalRoof for %s", postcode)
        
        data = {
            "postcode": postcode,
            "transport": {},
            "amenities": {"restaurants": [], "pubs": []},
            "affluence": {},
            "occupation": {},
            "ethnicity": {}
        }

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Use a fresh context per postcode to avoid session/modal persistent issues
            context = browser.new_context(
                user_agent=self._ua.random,
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            try:
                # 1. Transport
                url_transport = f"{self.BASE_URL}/{postcode_clean}/transport"
                soup = self._fetch_section(page, url_transport, "Transport Score")
                if soup:
                    data["transport"] = self._parse_transport(soup)

                # 2. Amenities
                url_amenities = f"{self.BASE_URL}/{postcode_clean}/amenities"
                soup = self._fetch_section(page, url_amenities, "Restaurants", click_show_more=True)
                if soup:
                    data["amenities"] = self._parse_amenities(soup)

                # 3. Affluence (Income)
                url_affluence = f"{self.BASE_URL}/{postcode_clean}/affluence"
                soup = self._fetch_section(page, url_affluence, "Household Income")
                if soup:
                    data["affluence"] = self._parse_affluence(soup)

                # 4. Occupation (under Affluence tab/query)
                url_occupation = f"{self.BASE_URL}/{postcode_clean}/affluence?tab=occupation"
                soup = self._fetch_section(page, url_occupation, "Occupations")
                if soup:
                    data["occupation"] = self._parse_occupation(soup)
                
                # 5. Demographics (Ethnicity)
                url_demo = f"{self.BASE_URL}/{postcode_clean}/demographics"
                soup = self._fetch_section(page, url_demo, "Ethnic Group")
                if soup:
                    data["ethnicity"] = self._parse_ethnicity(soup)

            finally:
                browser.close()

        logger.info("CrystalRoof scrape finished for %s", postcode)
        return data

    # ─── Navigation Logic ───────────────────────────────────

    def _fetch_section(self, page, url: str, wait_keyword: str, click_show_more: bool = False) -> Optional[BeautifulSoup]:
        """Navigate to a section, wait for content, and return Soup."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Add a small random jitter to navigation
                time.sleep(random.uniform(1, 3))
                
                logger.debug("Navigating to %s (attempt %d)", url, attempt)
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                
                # Wait for the main content area to appear
                try:
                    page.wait_for_selector("main article", timeout=10000)
                except Exception:
                    # If it doesn't appear, maybe it's a slow load or a 404
                    pass
                
                # Extra wait for network to settle and JS to run
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(2)
                
                content = page.content()
                
                # Robust "not found" check
                # Note: "No report found" might be in a hidden div or meta tag.
                # We check for a common "empty" state indicator.
                if "No report found" in content or "404 - Page not found" in content or "terminated" in content.lower() and "no longer active" in content.lower():
                    # Terminated postcodes still have some data, so we don't necessarily abort if we see "terminated"
                    if "No report found" in content:
                        logger.warning("CrystalRoof: No report found for %s", url)
                        return None

                if click_show_more:
                    try:
                        # Click ALL 'Show more' buttons (Bars/Pubs and Restaurants)
                        buttons = page.query_selector_all("button:has-text('Show more')")
                        for btn in buttons:
                            if btn.is_visible():
                                btn.click()
                                time.sleep(0.5)
                    except Exception:
                        pass

                return BeautifulSoup(content, "html.parser")
            except Exception as e:
                logger.debug("Attempt %d failed for %s: %s", attempt, url, e)
                if attempt == MAX_RETRIES:
                    logger.warning("Failed to fetch %s after %d retries", url, MAX_RETRIES)
                time.sleep(RETRY_DELAY_SECS)
        return None

    # ─── Parsing Logic ──────────────────────────────────────

    def _parse_transport(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /transport."""
        results = {
            "score": 0,
            "zone": "N/A",
            "stations": [],
            "distance_to_nearest": 0.0,
            "nearest_type": "N/A"
        }
        
        # Transport Score
        # Research: span inside Ez_A Br_C or similar
        score_container = soup.find("div", class_=re.compile("Ez_A|Br_C"))
        if score_container:
            text = score_container.get_text(strip=True)
            match = re.search(r"(\d)/9", text)
            if match:
                results["score"] = int(match.group(1))

        # Zone
        zone_label = soup.find(string=re.compile("Travel Zone", re.I))
        if zone_label:
            zone_val = zone_label.find_next("div") or zone_label.parent.find_next("div")
            if zone_val:
                results["zone"] = zone_val.get_text(strip=True)

        # Stations
        # Research: ul[data-transport-stations-list="true"]
        ul = soup.find("ul", attrs={"data-transport-stations-list": "true"})
        stations = []
        if ul:
            items = ul.find_all("li")
            for item in items:
                # Name and distance in p.Bq_E span.Bq_F
                p_tag = item.find("p", class_=re.compile("Bq_E"))
                if not p_tag: continue
                
                full_text = p_tag.get_text(strip=True)
                dist_span = p_tag.find("span", class_=re.compile("Bq_F"))
                dist_text = dist_span.get_text(strip=True) if dist_span else ""
                
                # Extract distance
                match = re.search(r"([\d\.]+)\s*miles?", dist_text)
                dist = float(match.group(1)) if match else 0.0
                
                # Extract name
                name = full_text.replace(dist_text, "").strip()
                
                # Lines / Type
                # Lines are usually in other tags within the li
                spans = item.find_all("span")
                lines = [s.get_text(strip=True) for s in spans if "mile" not in s.get_text().lower()]
                
                station_type = "Train"
                if any(kw in " ".join(lines).lower() for kw in ["underground", "tube", "metropolitan", "central", "northern", "piccadilly", "jubilee", "victoria", "circle", "district", "hammersmith", "bakerloo", "elizabeth"]):
                    station_type = "Underground"
                elif any(kw in " ".join(lines).lower() for kw in ["overground", "dlr", "tram"]):
                    station_type = "Overground"

                stations.append({
                    "name": name,
                    "distance": dist,
                    "type": station_type,
                    "lines": lines
                })

        if stations:
            stations.sort(key=lambda x: x["distance"])
            results["stations"] = stations
            results["distance_to_nearest"] = stations[0]["distance"]
            results["nearest_type"] = stations[0]["type"]

        return results

    def _parse_amenities(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /amenities."""
        results = {"restaurants": [], "pubs": []}
        
        # Research shows headers have data-items-list-title="true"
        headers = soup.find_all(["h2", "h3"], attrs={"data-items-list-title": "true"})
        for header in headers:
            header_text = header.get_text().lower()
            is_pub = "bar" in header_text or "pub" in header_text
            is_restaurant = "restaurant" in header_text or "cafe" in header_text
            
            if not (is_pub or is_restaurant):
                continue
                
            key = "pubs" if is_pub else "restaurants"
            
            # Find the UL sibling with data-unordered-list="true"
            # It's usually in a container div with the header
            container = header.find_parent("div", class_=re.compile("C7_C|Cg_C"))
            ul = (container.find("ul", attrs={"data-unordered-list": "true"}) 
                  if container else header.find_next("ul", attrs={"data-unordered-list": "true"}))
            
            if ul:
                items = ul.find_all("li", attrs={"data-unordered-item": "true"})
                for item in items:
                    name_span = item.find("span", attrs={"data-amenity-item": "true"})
                    if name_span:
                        full_text = name_span.get_text(strip=True)
                        dist_span = name_span.find("span", attrs={"data-color-ghost": "true"})
                        dist_text = dist_span.get_text(strip=True) if dist_span else ""
                        
                        name = full_text.replace(dist_text, "").strip()
                        results[key].append({"name": name, "distance": dist_text})
        
        return results

    def _parse_affluence(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /affluence."""
        results = {"income_pa": 0, "rating": "N/A"}
        
        # Household Income - Research: p[data-tile-value="true"] span.Ck_A
        income_tile = soup.find("p", attrs={"data-tile-value": "true"})
        if income_tile:
            text = income_tile.get_text(strip=True)
            # Use regex to extract the first numeric group after £
            match = re.search(r"£([\d,]+)", text)
            if match:
                results["income_pa"] = int(match.group(1).replace(",", ""))
        
        # Fallback for income if research attribute didn't match
        if results["income_pa"] == 0:
            income_spans = soup.find_all("span", class_=re.compile("Ck_A|headlineNumber"))
            for span in income_spans:
                txt = span.get_text(strip=True)
                match = re.search(r"£([\d,]+)", txt)
                if match:
                    results["income_pa"] = int(match.group(1).replace(",", ""))
                    break

        # Affluence Rating (e.g., "Well-off")
        rating_el = soup.find("div", attrs={"data-tile-score": "true"})
        if rating_el:
            score_span = rating_el.find("span")
            if score_span:
                results["rating"] = score_span.get_text(strip=True)

        return results

    def _parse_occupation(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /affluence?tab=occupation."""
        results = {}
        # Find the specific section for occupations to avoid comparison bars
        items = soup.find_all("div", attrs={"data-bar-chart-item": True})
        for item in items:
            label_container = item.find("span", attrs={"data-bar-chart-label": True})
            value_el = item.find("span", attrs={"data-bar-chart-value": True})
            
            if label_container and value_el:
                # Get the nested span for the clean label
                label_span = label_container.find("span", class_=re.compile("E8_D|E8_A"))
                label = label_span.get_text(strip=True).lower() if label_span else label_container.get_text(strip=True).lower()
                
                # Ignore comparison labels like "neighbourhood of..." or geographical regions
                if any(kw in label for kw in ["neighbourhood", "borough", "london", "immediate area"]):
                    continue
                    
                pct = self.safe_float(value_el.get_text())
                results[label] = pct
        return results

    def _parse_ethnicity(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /demographics."""
        results = {"white": 0.0, "non_white": 0.0, "details": {}}
        items = soup.find_all("div", attrs={"data-bar-chart-item": True})
        
        white_pct = 0.0
        for item in items:
            label_el = item.find("span", attrs={"data-bar-chart-label": True})
            value_el = item.find("span", attrs={"data-bar-chart-value": True})
            if label_el and value_el:
                label = label_el.get_text(strip=True).lower()
                pct = self.safe_float(value_el.get_text())
                results["details"][label] = pct
                
                if "white" in label and "mixed" not in label:
                    white_pct += pct
        
        if white_pct > 0 or results["details"]:
            results["white"] = round(white_pct / 100, 4)
            results["non_white"] = round(max(0, 100 - white_pct) / 100, 4)
            
        return results

    # ─── Data Normalization ──────────────────────────────────
    
    def get_social_grade_mapping(self, occupations: dict[str, float]) -> dict[str, float]:
        """Map NS-SEC occupations to AB, C1C2, DE."""
        # CrystalRoof occupation labels:
        # "managerial and professional"
        # "routine and manual"
        # "intermediate occupations"
        # "never worked / unemployed"
        # "full-time students"
        
        ab_total = occupations.get("managerial and professional", 0.0)
        c1c2_total = occupations.get("intermediate occupations", 0.0)
        # DE includes routine/manual and never worked
        de_total = occupations.get("routine and manual", 0.0) + occupations.get("never worked / unemployed", 0.0)
        
        # Normalize to 100% of non-students if needed, or just return percentages
        total = ab_total + c1c2_total + de_total
        if total > 0:
            return {
                "ab": round(ab_total / 100, 4),
                "c1_c2": round(c1c2_total / 100, 4),
                "de": round(de_total / 100, 4)
            }
        return {"ab": 0.0, "c1_c2": 0.0, "de": 0.0}
