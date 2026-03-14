import logging
import requests
import asyncio
from typing import Dict, Any

from location_analyzer.scrapers.streetcheck import DemographicsScraper
from location_analyzer.scrapers.crystalroof import CrystalRoofScraper

logger = logging.getLogger(__name__)

class InferencePipeline:
    """Orchestrates Phase 3 Scraping to gather live data for Phase 4 ML Inference."""
    
    def __init__(self):
        # Initialize scrapers
        self.demo_scraper = DemographicsScraper()
        self.cr_scraper = CrystalRoofScraper()
        
        # Scotland Support
        from location_analyzer.data.scotland_resolver import ScotlandResolver
        self.scotland_resolver = ScotlandResolver()

    def _get_outercode(self, postcode: str) -> str:
        """Extracts the outercode from a standard UK format postcode."""
        return postcode.strip().split()[0].upper()

    def _geocode_postcode(self, postcode: str, max_retries: int = 5) -> dict:
        """Resolve postcode to lat/lng via the free postcodes.io API with strict retries."""
        import time
        import random
        
        url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '%20')}"
        
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("result", {})
                    lat = data.get("latitude")
                    lng = data.get("longitude")
                    
                    if lat is not None and lng is not None:
                        return {
                            "lat": lat, 
                            "lng": lng,
                            "ward": data.get("admin_ward"),
                            "district": data.get("admin_district"),
                            "region": data.get("region")
                        }
                    else:
                        logger.warning("Geocoding API returned 200 but missing lat/lng on attempt %d for %s", attempt, postcode)
                elif resp.status_code == 404:
                    logger.warning("Geocoding API returned 404 (Not Found) for postcode %s", postcode)
                    return {} # Permanent failure, don't retry a 404
                else:
                    logger.warning("Geocoding API returned HTTP %d on attempt %d for %s", resp.status_code, attempt, postcode)
                    
            except Exception as e:
                logger.warning("Geocoding exception on attempt %d for %s: %s", attempt, postcode, e)
                
            if attempt < max_retries:
                # Exponential backoff: 2s, 4s, 8s, 16s... + jitter
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info("Retrying geocoding for %s in %.1fs...", postcode, sleep_time)
                time.sleep(sleep_time)
                
        logger.error("All %d geocoding attempts failed for %s. Map placement will be unavailable.", max_retries, postcode)
        return {}

    def _flatten_crystalroof(self, cr_data: dict) -> dict:
        """
        Flatten the nested CrystalRoof output into the flat column names 
        the ML model expects.
        """
        flat = {}

        # ── Transport ──────────────────────────────────────────
        transport = cr_data.get("transport", {})
        if isinstance(transport, dict):
            score = transport.get("score")
            if score is not None:
                try:
                    score_int = int(score)
                    if score_int > 0:
                        flat["Transport_Accessibility_Score"] = score_int
                except (ValueError, TypeError):
                    pass

            stations = transport.get("stations", [])
            if isinstance(stations, list) and stations:
                flat["Nearby_Station_Count"] = len(stations)
                nearest = stations[0]
                if isinstance(nearest, dict):
                    dist = nearest.get("distance")
                    if dist is not None:
                        try:
                            flat["Distance_to_Nearest_Station"] = float(dist)
                        except (ValueError, TypeError):
                            pass
                    stype = nearest.get("type")
                    if stype:
                        flat["Nearest_Station_Type"] = str(stype)
        
        return flat

    def run(self, postcode: str) -> Dict[str, Any]:
        """
        Full scraping + feature-assembly pipeline for one postcode.
        Logs input/output at every phase for better visibility.
        """
        postcode = postcode.strip().upper()
        outercode = self._get_outercode(postcode)

        logger.info(
            "\n"
            "┌──────────────────────────────────────────────────────────┐\n"
            "│  INFERENCE PIPELINE START  postcode=%-22s│\n"
            "└──────────────────────────────────────────────────────────┘",
            postcode,
        )

        # ── PHASE 0: Scotland Detection ───────────────────────────────────────
        if self.scotland_resolver.is_scottish(postcode):
            logger.info("  [PHASE 0] Scotland Detected. Routing to local resolver...")
            
            # 1. Geocode first to get lat/lng for transport/amenities calculations
            geo = self._geocode_postcode(postcode)
            lat, lng = geo.get("lat"), geo.get("lng")
            
            # 2. Resolve ML features using local Census/SIMD/Transport
            scot_features = self.scotland_resolver.get_features(postcode, lat=lat, lng=lng)
            
            if scot_features:
                scot_features.update(geo)
                scot_features["postcode"] = postcode
                scot_features["outercode"] = outercode
                logger.info("  [PHASE 0] Scotland resolution complete.")
                
                # 3. Hybrid Strategy: Rich Display Data (Local Demographics + Scraped Amenities)
                display_data = self.scotland_resolver.get_display_data(postcode, lat=lat, lng=lng)
                
                logger.info("  [PHASE 0.2] Fetching hybrid amenities (Restaurants/Pubs) from CrystalRoof...")
                try:
                    cr_data = self.cr_scraper.scrape(postcode)
                    if cr_data and "amenities" in cr_data:
                        display_data["amenities"] = cr_data["amenities"]
                        logger.info("  [PHASE 0.2] Hybrid amenities merged.")
                except Exception as e:
                    logger.warning("  [PHASE 0.2] CrystalRoof hybrid scrape failed: %s", e)
                
                scot_features["_display"] = display_data
                return scot_features
            else:
                logger.warning("  [PHASE 0] Scotland resolver returned empty results. Falling back to scrapers.")

        # ── PHASE 1: Demographics (Nomis API + Doogal) ────────────────────────
        logger.info("\n  [PHASE 1] Demographics Scraper (Nomis + Doogal)")
        try:
            demo_data = self.demo_scraper.scrape(postcode)
            logger.info(f"Demographics scraped: {demo_data}")
        except Exception as e:
            logger.error(f"Failed to scrape demographics for {postcode}: {e}")
            demo_data = {}

        # ── PHASE 2: CrystalRoof (Transport / Amenities / Ethnicity) ──────────
        logger.info("\n  [PHASE 2] CrystalRoof Scraper (Rich Data Extraction)")
        try:
            cr_data = self.cr_scraper.scrape(postcode)
            logger.info(f"CrystalRoof scraped: {cr_data}")
        except Exception as e:
            logger.error(f"Failed to scrape CrystalRoof for {postcode}: {e}")
            cr_data = {}

        # ── PHASE 3: Feature Assembly ──────────────────────────────────────────
        logger.info("\n  [PHASE 3] Feature Assembly & Model Key Mapping")
        combined = {}
        combined.update(demo_data)

        # Flatten CrystalRoof transport → model columns
        cr_flat = self._flatten_crystalroof(cr_data)
        combined.update(cr_flat)
        
        # Rename scraper keys → XGBoost expected feature names
        if 'c1_c2' in combined:
            combined['c1/c2'] = combined.pop('c1_c2')
        if 'non_white' in combined:
            combined['non-white'] = combined.pop('non_white')
            
        # Add basic identifiers
        combined['postcode'] = postcode
        combined['outercode'] = outercode

        # ── PHASE 4: Geocoding (Map Pin) ──────────────────────────────────────
        logger.info("\n  [PHASE 4] Geocoding (Postcodes.io)")
        geo = self._geocode_postcode(postcode)
        if geo:
            combined.update(geo)

        # ── PHASE 5: Attach Rich Display Data ─────────────────────────────────
        combined["_display"] = cr_data

        logger.info(
            "\n"
            "┌──────────────────────────────────────────────────────────┐\n"
            "│  INFERENCE PIPELINE COMPLETE                             │\n"
            "└──────────────────────────────────────────────────────────┘\n"
        )
        return combined
