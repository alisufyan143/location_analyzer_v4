"""
CrystalRoof Scraper - Fetches transport, amenities, affluence, and demographics data.
Source: crystalroof.co.uk
URL Pattern: https://crystalroof.co.uk/report/postcode/{postcode}/{section}

V2 Rewrite (March 2026): Uses TEXT-BASED & STRUCTURAL selectors only.
CrystalRoof rotates CSS class names on every rebuild, so we NEVER rely on them.
Instead, we match text patterns (regex), tag hierarchy, and visible content.
"""

import random
import time
import re
from typing import Any, Optional, List
from bs4 import BeautifulSoup, Tag
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

    V2: All selectors are text-based and resilient to CSS class rotation.

    Data collected across sub-pages:
    - /transport: Accessibility score, station names, distances, and lines.
    - /amenities: Pubs, restaurants, and supermarkets (names + distances).
    - /affluence: Household income and affluence rating.
    - /affluence?tab=occupation: Socio-economic breakdown (NS-SEC).
    - /demographics: Ethnicity validation.
    """

    CACHE_CATEGORY = "crystal"
    BASE_URL = "https://crystalroof.co.uk/report/postcode"

    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless

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
            browser = p.chromium.launch(headless=self.headless)
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

                # Dismiss any sign-in modal by pressing Escape
                try:
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
                except Exception:
                    pass

                # Wait for the main content area to appear
                try:
                    page.wait_for_selector("main", timeout=10000)
                except Exception:
                    pass

                # Extra wait for network to settle and JS to run
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                time.sleep(2)

                content = page.content()

                # Robust "not found" check
                if "No report found" in content or "404 - Page not found" in content:
                    logger.warning("CrystalRoof: No report found for %s", url)
                    return None

                if click_show_more:
                    try:
                        # Click ALL 'Show more' / 'Show X more' buttons
                        buttons = page.query_selector_all("button")
                        for btn in buttons:
                            btn_text = btn.inner_text().lower() if btn.is_visible() else ""
                            if "show" in btn_text and "more" in btn_text:
                                btn.click()
                                time.sleep(0.5)
                        # Re-read content after expanding
                        time.sleep(1)
                        content = page.content()
                    except Exception:
                        pass

                return BeautifulSoup(content, "html.parser")
            except Exception as e:
                logger.debug("Attempt %d failed for %s: %s", attempt, url, e)
                if attempt == MAX_RETRIES:
                    logger.warning("Failed to fetch %s after %d retries", url, MAX_RETRIES)
                time.sleep(RETRY_DELAY_SECS)
        return None

    # ─── Helper: Find text in page ──────────────────────────

    @staticmethod
    def _find_text_element(soup: BeautifulSoup, pattern: str, tag: Optional[str] = None) -> Optional[Tag]:
        """Find the first element whose text matches a regex pattern."""
        regex = re.compile(pattern, re.I)
        if tag:
            return soup.find(tag, string=regex)
        return soup.find(string=regex)

    @staticmethod
    def _extract_all_li_items(soup: BeautifulSoup, section_heading_pattern: str) -> List[Tag]:
        """Find all <li> items under a section identified by a heading text pattern."""
        heading = soup.find(string=re.compile(section_heading_pattern, re.I))
        if not heading:
            return []
        # Walk up to the heading's parent container, then find all li items
        parent = heading.find_parent()
        if parent:
            # Go up a few levels to find the section container
            for _ in range(5):
                parent = parent.parent
                if parent is None:
                    break
                lis = parent.find_all("li")
                if len(lis) >= 1:
                    return lis
        return []

    # ─── Parsing Logic (V2: Text-Based) ─────────────────────

    def _parse_transport(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /transport using text patterns only."""
        results = {
            "score": 0,
            "zone": "N/A",
            "stations": [],
            "distance_to_nearest": 0.0,
            "nearest_type": "N/A"
        }

        # ── Transport Score: Find "X/9" anywhere on the page ──
        full_text = soup.get_text()
        score_match = re.search(r'(\d)\s*/\s*9', full_text)
        if score_match:
            results["score"] = int(score_match.group(1))

        # ── Travel Zone: Find text "Travel Zone" then extract nearby number ──
        zone_el = soup.find(string=re.compile(r"Travel Zone", re.I))
        if zone_el:
            # Look in next siblings / parent's next siblings for the zone value
            parent = zone_el.find_parent()
            if parent:
                container = parent.find_parent()
                if container:
                    zone_text = container.get_text()
                    zone_match = re.search(r'(?:Zone|zone)\s*[:\s]*(\d+[a-zA-Z]?)', zone_text)
                    if zone_match:
                        results["zone"] = zone_match.group(1)
                    else:
                        # Fallback: find any standalone digit near "Zone"
                        zone_nums = re.findall(r'(?<!\d)(\d{1,2})(?!\d)', zone_text.replace("Travel Zone", ""))
                        if zone_nums:
                            results["zone"] = zone_nums[0]

        # ── Stations: Find all <li> elements containing "mile" ──
        stations = []
        all_lis = soup.find_all("li")
        for li in all_lis:
            li_text = li.get_text(strip=True)
            if not re.search(r'[\d.]+\s*miles?', li_text):
                continue

            # Extract distance
            dist_match = re.search(r'([\d.]+)\s*miles?', li_text)
            dist = float(dist_match.group(1)) if dist_match else 0.0

            # Extract name: everything before the distance value
            # Get the first <p> or text child for the name
            name_parts = []
            for child in li.children:
                if isinstance(child, Tag) and child.name == "p":
                    # The station name is typically in the first <p>
                    p_text = child.get_text(strip=True)
                    # Remove the distance part from the name
                    name = re.sub(r'[\d.]+\s*miles?', '', p_text).strip()
                    if name:
                        name_parts.append(name)
                    break

            if not name_parts:
                # Fallback: take text before the distance
                name = re.sub(r'[\d.]+\s*miles?.*', '', li_text).strip()
                name_parts = [name] if name else []

            if not name_parts:
                continue

            station_name = name_parts[0]

            # Determine station type from the full text of the li
            station_type = self._classify_station_type(li_text)

            stations.append({
                "name": station_name,
                "distance": dist,
                "type": station_type,
                "lines": []
            })

        if stations:
            stations.sort(key=lambda x: x["distance"])
            results["stations"] = stations
            results["distance_to_nearest"] = stations[0]["distance"]
            results["nearest_type"] = stations[0]["type"]

        return results

    @staticmethod
    def _classify_station_type(text: str) -> str:
        """Classify station type from surrounding text."""
        t = text.lower()
        underground_keywords = [
            "underground", "tube", "metropolitan", "central line",
            "northern line", "piccadilly", "jubilee", "victoria line",
            "circle", "district", "hammersmith", "bakerloo", "elizabeth"
        ]
        overground_keywords = ["overground", "dlr", "tram", "tramlink"]

        if any(kw in t for kw in underground_keywords):
            return "Underground"
        elif any(kw in t for kw in overground_keywords):
            return "Overground"
        return "Train"

    def _parse_amenities(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /amenities using section headings and text patterns."""
        results = {"restaurants": [], "pubs": []}

        # Strategy: Find section headings containing "Restaurant" or "Bar/Pub"
        # then collect all list items below them
        all_headings = soup.find_all(["h2", "h3", "h4"])

        for heading in all_headings:
            heading_text = heading.get_text(strip=True).lower()

            is_pub = "bar" in heading_text or "pub" in heading_text or "club" in heading_text
            is_restaurant = "restaurant" in heading_text or "cafe" in heading_text

            if not (is_pub or is_restaurant):
                continue

            key = "pubs" if is_pub else "restaurants"

            # Walk up to the section container, then find all <li> items
            container = heading.find_parent("div") or heading.find_parent("section")
            if not container:
                continue

            # Find all list items in this section
            items = container.find_all("li")
            for item in items:
                item_text = item.get_text(strip=True)
                if not item_text or len(item_text) < 3:
                    continue

                # Extract distance (e.g., "65 yards", "0.1 miles", "320 yards")
                dist_match = re.search(r'([\d.]+\s*(?:yards?|miles?|mi|m))', item_text)
                dist_text = dist_match.group(1) if dist_match else ""

                # Name is text minus the distance
                name = item_text.replace(dist_text, "").strip()
                # Clean trailing/leading punctuation
                name = re.sub(r'^[\s\-–]+|[\s\-–]+$', '', name)

                if name:
                    results[key].append({"name": name, "distance": dist_text})

        return results

    def _parse_affluence(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Parsed from /affluence using text patterns for £ amounts and X/10 scores."""
        results = {"income_pa": 0, "rating": "N/A"}

        full_text = soup.get_text()

        # ── Household Income: Find "£XX,XXX" pattern ──
        # Strategy: Find all £ amounts and take the one near "household income"
        income_matches = re.findall(r'£([\d,]+)', full_text)
        if income_matches:
            # Take the first match (usually the prominent one)
            results["income_pa"] = int(income_matches[0].replace(",", ""))

        # ── Affluence Rating: Find "X/10" pattern ──
        rating_match = re.search(r'(\d+)\s*/\s*10', full_text)
        if rating_match:
            results["rating"] = f"{rating_match.group(1)}/10"

        return results

    def _parse_occupation(self, soup: BeautifulSoup) -> dict[str, Any]:
        """
        Parsed from /affluence?tab=occupation.
        Scans the page text for known NS-SEC occupation labels and their percentages.
        """
        results = {}

        # Known occupation categories to search for
        OCCUPATION_LABELS = [
            "managerial and professional",
            "intermediate occupations",
            "routine and manual",
            "never worked",
            "full-time students",
        ]

        # Geographic/comparison labels to skip
        GEO_SKIP = [
            "neighbourhood", "borough", "london", "immediate area",
            "local authority", "midlands", "england", "region", "national",
            "scotland", "wales", "uk average", "city", "district", "county",
        ]

        full_text = soup.get_text()

        # Strategy 1: Look for "Label XX%" patterns in the full text
        for label in OCCUPATION_LABELS:
            # Match the label followed by a percentage somewhere nearby
            pattern = re.compile(
                re.escape(label) + r'[^%]*?(\d+(?:\.\d+)?)\s*%',
                re.I | re.DOTALL
            )
            match = pattern.search(full_text)
            if match:
                results[label] = float(match.group(1))

        # Strategy 2: If Strategy 1 found nothing, try parsing structured elements
        if not results:
            # Look for elements that look like bar chart rows
            # Pattern: find all <dd> or <div> elements with "%" text
            for el in soup.find_all(True):
                el_text = el.get_text(strip=True)
                # Skip geographic comparisons
                if any(geo in el_text.lower() for geo in GEO_SKIP):
                    continue
                # Look for label + percentage pattern
                for label in OCCUPATION_LABELS:
                    if label in el_text.lower():
                        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', el_text)
                        if pct_match and label not in results:
                            results[label] = float(pct_match.group(1))

        return results

    # ─── Ethnicity/demographics section keywords ─────────────
    _RELIGION_KW = {"christian", "muslim", "sikh", "hindu", "jewish", "buddhist",
                    "no religion", "religion not stated", "other religion"}
    _AGE_KW = {"aged"}
    _HOUSEHOLD_KW = {"families", "people living", "households", "extended families",
                     "other family"}

    @classmethod
    def _classify_detail_row(cls, label: str) -> str:
        """Return section name for an ethnicity-page row."""
        l = label.lower()
        if any(kw in l for kw in cls._AGE_KW):       return "Age"
        if any(kw in l for kw in cls._HOUSEHOLD_KW): return "Household"
        if any(kw in l for kw in cls._RELIGION_KW):  return "Religion"
        return "Ethnicity"

    @staticmethod
    def _clean_detail_key(raw: str) -> str:
        """Strip trailing percentage digits from label, e.g. 'white british32%' → 'White British'."""
        cleaned = re.sub(r'[\d\.]+%?\s*$', '', raw).strip()
        return cleaned.title() if cleaned else raw.title()

    def _parse_ethnicity(self, soup: BeautifulSoup) -> dict[str, Any]:
        """
        Parsed from /demographics.
        V2: Uses text patterns to extract ethnicity/religion/age data.
        Returns categorized sections + top-level white/non_white.
        """
        sections: dict[str, list[dict]] = {
            "Ethnicity": [], "Religion": [], "Age": [], "Household": []
        }

        full_text = soup.get_text()
        white_pct = 0.0
        total_eth = 0.0

        # Known ethnicity labels to search for
        ETH_LABELS = [
            "white british", "white irish", "white other", "white",
            "indian", "pakistani", "bangladeshi", "chinese",
            "other asian", "black african", "black caribbean",
            "other black", "mixed", "arab", "other ethnic",
        ]

        RELIGION_LABELS = [
            "christian", "muslim", "hindu", "sikh", "jewish",
            "buddhist", "no religion", "religion not stated", "other religion"
        ]

        AGE_LABELS = [
            "aged 0 to 15", "aged 16 to 19", "aged 20 to 39",
            "aged 40 to 59", "aged 60 to 79", "aged 80"
        ]

        # Parse ethnicity data
        for label in ETH_LABELS:
            pattern = re.compile(
                re.escape(label) + r'[^%]*?(\d+(?:\.\d+)?)\s*%',
                re.I | re.DOTALL
            )
            match = pattern.search(full_text)
            if match:
                pct = float(match.group(1))
                clean_label = label.title()
                sections["Ethnicity"].append({"name": clean_label, "pct": pct})
                total_eth += pct
                if "white" in label.lower() and "mixed" not in label.lower():
                    white_pct += pct

        # Parse religion data
        for label in RELIGION_LABELS:
            pattern = re.compile(
                re.escape(label) + r'[^%]*?(\d+(?:\.\d+)?)\s*%',
                re.I | re.DOTALL
            )
            match = pattern.search(full_text)
            if match:
                pct = float(match.group(1))
                sections["Religion"].append({"name": label.title(), "pct": pct})

        # Parse age data
        for label in AGE_LABELS:
            pattern = re.compile(
                re.escape(label) + r'[^%]*?(\d+(?:\.\d+)?)\s*%',
                re.I | re.DOTALL
            )
            match = pattern.search(full_text)
            if match:
                pct = float(match.group(1))
                sections["Age"].append({"name": label.title(), "pct": pct})

        non_white_pct = max(0.0, total_eth - white_pct)
        return {
            "white":     round(white_pct / 100, 4) if total_eth else 0.0,
            "non_white": round(non_white_pct / 100, 4) if total_eth else 0.0,
            "sections":  sections,
        }

    # ─── Data Normalization ──────────────────────────────────

    def get_social_grade_mapping(self, occupations: dict[str, float]) -> dict[str, float]:
        """Map NS-SEC occupations to AB, C1C2, DE."""
        ab_total = occupations.get("managerial and professional", 0.0)
        c1c2_total = occupations.get("intermediate occupations", 0.0)
        de_total = occupations.get("routine and manual", 0.0) + occupations.get("never worked", 0.0)

        total = ab_total + c1c2_total + de_total
        if total > 0:
            return {
                "ab": round(ab_total / 100, 4),
                "c1_c2": round(c1c2_total / 100, 4),
                "de": round(de_total / 100, 4)
            }
        return {"ab": 0.0, "c1_c2": 0.0, "de": 0.0}
