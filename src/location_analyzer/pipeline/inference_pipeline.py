import logging
import requests
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
        
    def _get_outercode(self, postcode: str) -> str:
        """Extracts the outercode from a standard UK format postcode."""
        return postcode.strip().split()[0].upper()

    def _geocode_postcode(self, postcode: str) -> dict:
        """Resolve postcode to lat/lng via the free postcodes.io API."""
        try:
            url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '%20')}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                return {"lat": data.get("latitude"), "lng": data.get("longitude")}
        except Exception as e:
            logger.warning("Geocoding failed for %s: %s", postcode, e)
        return {}

    def _flatten_crystalroof(self, cr_data: dict) -> dict:
        """
        Flatten the nested CrystalRoof output into the flat column names 
        the ML model expects.
        
        CrystalRoof returns:
            transport: {score, zone, stations: [{name, distance, type, lines}...]}
            affluence: {income_pa, rating}
            
        Model expects:
            Transport_Accessibility_Score  (int, 1-10)
            Nearby_Station_Count           (int)
            Distance_to_Nearest_Station    (float, miles)
            Nearest_Station_Type           (str, e.g. "Underground", "National Rail")
        """
        flat = {}

        # ── Transport ──────────────────────────────────────────
        transport = cr_data.get("transport", {})
        if isinstance(transport, dict):
            # Transport Score → Transport_Accessibility_Score
            score = transport.get("score")
            if score is not None:
                try:
                    flat["Transport_Accessibility_Score"] = int(score)
                except (ValueError, TypeError):
                    pass

            # Stations list → station count, nearest distance, nearest type
            stations = transport.get("stations", [])
            if isinstance(stations, list) and stations:
                flat["Nearby_Station_Count"] = len(stations)

                # First station is the nearest (CrystalRoof lists by distance)
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
        Executes the scraping pipeline for a given postcode and formats the 
        output dictionary into the exact schema expected by XGBoost `PredictionService`.
        """
        logger.info(f"Starting Inference Pipeline for Postcode: {postcode}")
        
        outercode = self._get_outercode(postcode)
        
        # 1. Scrape Demographics (Nomis API + Doogal)
        try:
            demo_data = self.demo_scraper.scrape(postcode)
            logger.info(f"Demographics scraped: {demo_data}")
        except Exception as e:
            logger.error(f"Failed to scrape demographics for {postcode}: {e}")
            demo_data = {}

        # 2. Scrape CrystalRoof for Transport/Amenities
        try:
            cr_data = self.cr_scraper.scrape(postcode)
            logger.info(f"CrystalRoof scraped: {cr_data}")
        except Exception as e:
            logger.error(f"Failed to scrape CrystalRoof for {postcode}: {e}")
            cr_data = {}

        # 3. Combine into unified flat format
        combined = {}
        combined.update(demo_data)

        # Flatten CrystalRoof transport → model columns
        cr_flat = self._flatten_crystalroof(cr_data)
        combined.update(cr_flat)
        
        # 4. Rename scraper keys → XGBoost expected feature names
        if 'c1_c2' in combined:
            combined['c1/c2'] = combined.pop('c1_c2')
        if 'non_white' in combined:
            combined['non-white'] = combined.pop('non_white')
            
        # Add basic identifiers
        combined['postcode'] = postcode
        combined['outercode'] = outercode

        # 5. Geocode the postcode for the map pin
        geo = self._geocode_postcode(postcode)
        if geo:
            combined.update(geo)
        
        return combined
