"""
Demographics data provider for UK postcodes.

Primary source:   Nomis REST API  (Census 2021 – official ONS data, no browser)
Secondary source: Doogal.co.uk    (avg_household_income – lightweight HTML)

Output matches training dataset columns 8-18:
    population, households, avg_household_income, unemployment_rate,
    working, unemployed, ab, c1_c2, de, white, non_white

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nomis API (https://www.nomisweb.co.uk/api/v01/help):
    Geography:  POSTCODE|{postcode};{type}
                type 150 = Census 2021 Output Areas (finest)
    Datasets:
        NM_2021_1  (TS001) — Population
        NM_2023_1  (TS003) — Households
        NM_2041_1  (TS021) — Ethnic Group
        NM_2079_1  (TS062) — NS-SeC (maps to AB / C1C2 / DE)
        NM_2083_1  (TS066) — Economic Activity

    Authenticated via optional uid param (removes 25K cell limit).
    Returns CSV with labelled category columns.

Doogal (https://www.doogal.co.uk/ShowMap?postcode=...):
    Static HTML page.  "Average household income (2020)" field.
    Scraped with simple GET + BeautifulSoup – no JS rendering needed.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Updated: 2026-02-23  (replaced Playwright-based postcodearea/streetcheck scrapers)
"""

import csv
import io
import re
from typing import Any

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from location_analyzer.scrapers.base import BaseScraper
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import ScraperParsingError

logger = get_logger(__name__)

# ─── Nomis API Constants ─────────────────────────────────
NOMIS_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
GEO_TYPE = 150  # Census 2021 Output Areas

# Dataset IDs (Census 2021 Topic Summaries)
DS_POPULATION = "NM_2021_1"   # TS001
DS_HOUSEHOLDS = "NM_2023_1"   # TS003
DS_ETHNICITY  = "NM_2041_1"   # TS021
DS_NSSEC      = "NM_2079_1"   # TS062  (NS-SeC → maps to AB/C1C2/DE)
DS_ECON       = "NM_2083_1"   # TS066  (Economic Activity)

# Doogal
DOOGAL_URL = "https://www.doogal.co.uk/ShowMap?postcode={postcode}"


# ─── Helper: Nomis CSV fetch ────────────────────────────
def _nomis_csv(dataset_id: str, postcode: str, uid: str | None = None) -> list[dict]:
    """
    Query one Nomis Census 2021 dataset for a postcode.

    Args:
        uid: Optional Nomis API UID for authenticated access
             (removes 25K cell limit, prevents rate-limiting).

    Returns a list of dicts (one per CSV row) with keys from the header.
    Raises ScraperParsingError on non-200 or empty responses.
    """
    pc_encoded = postcode.strip().replace(" ", "+")
    url = (
        f"{NOMIS_BASE}/{dataset_id}.data.csv"
        f"?geography=POSTCODE|{pc_encoded};{GEO_TYPE}"
        f"&measures=20100"
    )
    if uid:
        url += f"&uid={uid}"
    logger.debug("Nomis request: %s", url)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        raise ScraperParsingError(
            message=f"Nomis returned empty data for {dataset_id} / {postcode}",
            details={"dataset": dataset_id, "postcode": postcode},
        )

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ScraperParsingError(
            message=f"Nomis CSV had no data rows for {dataset_id} / {postcode}",
            details={"dataset": dataset_id, "postcode": postcode},
        )
    return rows


def _find_name_col(rows: list[dict], prefix: str) -> str | None:
    """
    Dynamically find the NAME column for a given concept prefix.

    Nomis column names vary (e.g. C2021_ETH_20_NAME vs C2021_ETH_9_NAME)
    depending on which classification variant the dataset uses. This finds
    the correct one by scanning keys of the first row.
    """
    if not rows:
        return None
    for key in rows[0].keys():
        if key.startswith(prefix) and key.endswith("_NAME"):
            return key
    return None


def _find_row_value(rows: list[dict], name_col: str, search_term: str) -> int:
    """Find the OBS_VALUE of the first row whose name_col matches search_term exactly."""
    for row in rows:
        label = (row.get(name_col) or "").strip()
        if label == search_term:
            try:
                return int(row.get("OBS_VALUE", 0))
            except (ValueError, TypeError):
                return 0
    return 0


def _find_row_contains(rows: list[dict], name_col: str, substring: str) -> int:
    """Find the OBS_VALUE of the first row whose name_col contains substring."""
    for row in rows:
        label = (row.get(name_col) or "").strip()
        if substring.lower() in label.lower():
            try:
                return int(row.get("OBS_VALUE", 0))
            except (ValueError, TypeError):
                return 0
    return 0


def _total_row(rows: list[dict]) -> int:
    """Return the OBS_VALUE of the first row (which is always the Total)."""
    try:
        return int(rows[0].get("OBS_VALUE", 0))
    except (ValueError, TypeError, IndexError):
        return 0


def _pct(part: float, total: float) -> float:
    """Safe fraction calculation (0.0–1.0 scale, matching ML model training format)."""
    return round(part / total, 3) if total else 0.0


# ─── Main Scraper ────────────────────────────────────────
class DemographicsScraper(BaseScraper):
    """
    Fetches postcode demographics via the Nomis Census 2021 REST API
    and average household income from Doogal.co.uk (via Playwright).

    No proxy or anti-bot bypass required.

    Args:
        headless: If False, the Playwright browser opens visibly for debugging.
    """

    CACHE_CATEGORY = "demographics"

    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless
        # Load Nomis API key from config (if available)
        try:
            from location_analyzer.config import settings
            self._nomis_uid = settings.scraper.nomis_api_uid
        except Exception:
            self._nomis_uid = None

    def scrape(self, postcode: str) -> dict[str, Any]:
        """
        Fetch all demographic fields for a UK postcode (or outercode).

        Accepts both full postcodes (e.g. "UB5 5AF") and outercodes
        (e.g. "UB5"). Outercodes are resolved by the Nomis POSTCODE
        lookup which may return aggregate Output Area data.

        Returns:
            Dict with keys: population, households, avg_household_income,
            unemployment_rate, working, unemployed, ab, c1_c2, de,
            white, non_white.
        """
        postcode = postcode.strip().upper()
        logger.info("Fetching demographics for %s via Nomis API + Doogal", postcode)

        result: dict[str, Any] = {}

        # ── 1. Population (TS001) ───────────────────────────
        try:
            pop_rows = _nomis_csv(DS_POPULATION, postcode, self._nomis_uid)
            result["population"] = _total_row(pop_rows)
            logger.info("Population: %s", result["population"])
        except Exception as e:
            logger.warning("Nomis population failed: %s", e)
            result["population"] = 0

        # ── 2. Households (TS003) ───────────────────────────
        try:
            hh_rows = _nomis_csv(DS_HOUSEHOLDS, postcode, self._nomis_uid)
            result["households"] = _total_row(hh_rows)
            logger.info("Households: %s", result["households"])
        except Exception as e:
            logger.warning("Nomis households failed: %s", e)
            result["households"] = 0

        # ── 3. Ethnicity (TS021) ────────────────────────────
        try:
            eth_rows = _nomis_csv(DS_ETHNICITY, postcode, self._nomis_uid)
            total_eth = _total_row(eth_rows)

            # Dynamically find the NAME column (could be C2021_ETH_20_NAME or C2021_ETH_9_NAME)
            name_col = _find_name_col(eth_rows, "C2021_ETH")
            logger.debug("Ethnicity name column: %s", name_col)

            if name_col:
                white_count = _find_row_value(eth_rows, name_col, "White")
            else:
                white_count = 0

            non_white_count = total_eth - white_count
            result["white"] = _pct(white_count, total_eth)
            result["non_white"] = _pct(non_white_count, total_eth)
            logger.info("Ethnicity: white=%.1f%%, non_white=%.1f%%",
                        result["white"], result["non_white"])
        except Exception as e:
            logger.warning("Nomis ethnicity failed: %s", e)
            result["white"] = 0.0
            result["non_white"] = 0.0

        # ── 4. Economic Activity (TS066) ────────────────────
        try:
            econ_rows = _nomis_csv(DS_ECON, postcode, self._nomis_uid)
            total_econ = _total_row(econ_rows)  # All residents 16+

            # Dynamically find the NAME column (e.g. C2021_EASTAT_20_NAME)
            name_col = _find_name_col(econ_rows, "C2021_EASTAT")
            logger.debug("Economic activity name column: %s", name_col)

            # Sum up employed and unemployed from labelled rows
            employed = 0
            unemployed = 0

            if name_col:
                for row in econ_rows:
                    label = (row.get(name_col) or "").strip()
                    val = int(row.get("OBS_VALUE", 0) or 0)

                    # Main "In employment" aggregates (excl. sub-breakdowns)
                    if label == "Economically active (excluding full-time students):In employment":
                        employed += val
                    elif label == "Economically active and a full-time student:In employment":
                        employed += val

                    # Unemployed aggregates
                    elif label == "Economically active (excluding full-time students): Unemployed":
                        unemployed += val
                    elif label == "Economically active and a full-time student: Unemployed":
                        unemployed += val

            result["working"] = _pct(employed, total_econ)
            result["unemployed"] = _pct(unemployed, total_econ)
            result["unemployment_rate"] = result["unemployed"]
            logger.info("Employment: working=%.1f%%, unemployed=%.1f%%",
                        result["working"], result["unemployed"])
        except Exception as e:
            logger.warning("Nomis economic activity failed: %s", e)
            result["working"] = 0.0
            result["unemployed"] = 0.0
            result["unemployment_rate"] = 0.0

        # ── 5. NS-SeC → Social Grades AB/C1C2/DE (TS062) ───
        try:
            nssec_rows = _nomis_csv(DS_NSSEC, postcode, self._nomis_uid)
            total_nssec = _total_row(nssec_rows)

            # Dynamically find the NAME column
            name_col = _find_name_col(nssec_rows, "C2021_NSSEC")
            logger.debug("NS-SeC name column: %s", name_col)

            # NS-SeC mapping to traditional social grades:
            #   AB = L1-L3 (Higher managerial) + L4-L6 (Lower managerial)
            #   C1/C2 = L7 (Intermediate) + L8-L9 (Small employers) + L10-L11 (Lower supervisory)
            #   DE = L12 (Semi-routine) + L13 (Routine) + L14 (Never worked/long-term unemployed)
            ab_count = 0
            c1c2_count = 0
            de_count = 0

            if name_col:
                for row in nssec_rows:
                    label = (row.get(name_col) or "").strip()
                    val = int(row.get("OBS_VALUE", 0) or 0)

                    if "L1, L2 and L3" in label:       # Higher managerial
                        ab_count += val
                    elif "L4, L5 and L6" in label:      # Lower managerial
                        ab_count += val
                    elif "L7 Intermediate" in label:    # Intermediate
                        c1c2_count += val
                    elif "L8 and L9" in label:          # Small employers
                        c1c2_count += val
                    elif "L10 and L11" in label:        # Lower supervisory
                        c1c2_count += val
                    elif "L12 Semi-routine" in label:   # Semi-routine
                        de_count += val
                    elif "L13 Routine" in label:        # Routine
                        de_count += val
                    elif "L14" in label:                # Never worked / long-term unemployed
                        de_count += val

            result["ab"] = _pct(ab_count, total_nssec)
            result["c1_c2"] = _pct(c1c2_count, total_nssec)
            result["de"] = _pct(de_count, total_nssec)
            logger.info("Social grades: AB=%.1f%%, C1C2=%.1f%%, DE=%.1f%%",
                        result["ab"], result["c1_c2"], result["de"])
        except Exception as e:
            logger.warning("Nomis NS-SeC failed: %s", e)
            result["ab"] = 0.0
            result["c1_c2"] = 0.0
            result["de"] = 0.0

        # ── 6. Avg Household Income (Doogal) ────────────────
        try:
            result["avg_household_income"] = self._fetch_doogal_income(postcode)
            logger.info("Avg household income: £%s", result["avg_household_income"])
        except Exception as e:
            logger.warning("Doogal income scrape failed: %s", e)
            result["avg_household_income"] = 0

        logger.info("Demographics complete for %s: %s", postcode, result)
        return result

    # ─── Doogal Income Scraper (Playwright) ───────────────────
    def _fetch_doogal_income(self, postcode: str) -> int:
        """
        Scrape average household income from doogal.co.uk using Playwright.

        Opens a browser (visible if headless=False), navigates to the Doogal
        postcode map page, waits for content, and extracts the income value.
        Retries up to 2 times on timeout.

        Returns the income as an integer (e.g. 68500), or 0 on failure.
        """
        pc_encoded = postcode.replace(" ", "%20")
        url = DOOGAL_URL.format(postcode=pc_encoded)
        logger.info("Doogal request (Playwright, headless=%s): %s", self.headless, url)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                return self._fetch_doogal_income_attempt(url, postcode, attempt)
            except Exception as e:
                logger.warning(
                    "Doogal attempt %d/%d failed for %s: %s",
                    attempt, max_attempts, postcode, e,
                )
                if attempt == max_attempts:
                    return 0

        return 0

    def _fetch_doogal_income_attempt(self, url: str, postcode: str, attempt: int) -> int:
        """Single attempt to fetch income from Doogal via Playwright."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=40000, wait_until="domcontentloaded")
                # Wait for the demographics section to render
                page.wait_for_timeout(3000)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # ── Strategy 1: Exact Doogal structure ──────────────
                # <th>Average household income (2020) ...</th>
                # <td colspan="2">
                #   <div class="progress">
                #     <div class="progress-bar">
                #       <span class="show">£68,500</span>
                for th in soup.find_all("th"):
                    text = th.get_text(strip=True)
                    if "average household income" in text.lower():
                        next_td = th.find_next_sibling("td")
                        if next_td:
                            # Look for <span class="show"> inside the progress bar
                            span = next_td.find("span", class_="show")
                            if span:
                                match = re.search(r"£([\d,]+)", span.get_text(strip=True))
                                if match:
                                    income = int(match.group(1).replace(",", ""))
                                    logger.info("Doogal income found (span.show): £%s", f"{income:,}")
                                    return income
                            # Fallback: any £ amount in the td
                            match = re.search(r"£([\d,]+)", next_td.get_text())
                            if match:
                                income = int(match.group(1).replace(",", ""))
                                logger.info("Doogal income found (td text): £%s", f"{income:,}")
                                return income

                # ── Strategy 2: Also check <td> labels (in case structure changes)
                for td in soup.find_all("td"):
                    text = td.get_text(strip=True)
                    if "average household income" in text.lower():
                        next_td = td.find_next_sibling("td")
                        if next_td:
                            match = re.search(r"£([\d,]+)", next_td.get_text())
                            if match:
                                income = int(match.group(1).replace(",", ""))
                                logger.info("Doogal income found (td fallback): £%s", f"{income:,}")
                                return income

                # ── Strategy 3: Full-page regex as last resort
                page_text = soup.get_text()
                match = re.search(
                    r"average\s+household\s+income.*?£([\d,]+)",
                    page_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if match:
                    income = int(match.group(1).replace(",", ""))
                    logger.info("Doogal income found (regex): £%s", f"{income:,}")
                    return income

                logger.warning("Could not find income on Doogal for %s", postcode)
                return 0

            finally:
                context.close()
                browser.close()

