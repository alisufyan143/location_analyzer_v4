"""
Standardized resolver for Scottish location demographics and transport metrics.
Provides 1:1 parity with legacy scrapers but using official Scottish datasets.
"""

import csv
import math
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from location_analyzer.config import settings

logger = logging.getLogger(__name__)

class ScotlandResolver:
    """
    Critically resolves Scotland-specific features for the V3 ML pipeline.
    Uses local SSPL, SIMD, and Census 2022 bulk data.
    """

    def __init__(self):
        self.config = settings.scotland
        self.stations = self._load_stations()
        self.census_cache = None # Lazy load
        self.simd_cache = None   # Lazy load
        self.income_cache = None # Lazy load

    def is_scottish(self, postcode: str) -> bool:
        """Determines if a postcode belongs to Scotland via SSPL lookup."""
        pc_clean = postcode.replace(" ", "").upper()
        # Fast check: If we have it in SSPL, it's Scotland.
        with open(settings.scotland.sspl_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row[0].replace(" ", "").upper() == pc_clean:
                    return True
        return False

    def get_features(self, postcode: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
        """
        Resolves the demographic and transport features for a Scottish postcode.
        
        Critically:
        - Percentages are returned as decimals (0.0 to 1.0).
        - Distances are returned in miles.
        """
        pc_clean = postcode.replace(" ", "").upper()
        dz22, dz11 = self._resolve_data_zones(pc_clean)
        
        if not dz22 or not dz11:
            logger.warning("Could not resolve Data Zones for Scottish postcode: %s", postcode)
            return {}

        # Lazy load caches
        if self.census_cache is None: self.census_cache = self._cache_census()
        if self.simd_cache is None: self.simd_cache = self._cache_simd()
        if self.income_cache is None: self.income_cache = self._cache_income()

        features = {
            "postcode": postcode,
            "dz2011": dz11,
            "dz2022": dz22,
        }

        # 1. Economic (SIMD/Income) - 2011 Based
        if dz11 in self.simd_cache:
            s = self.simd_cache[dz11]
            features["unemployment_rate"] = round(float(s.get('Employment_rate', 0)), 4)
            features["unemployed"] = int(s.get("Employment_count", 0))
            features["working"] = int(s.get("Working_age_population", 0))
            features["population"] = int(s.get("Total_population", 0))
            
            # Accessibility Score Mapping
            score = (self._map_acc_score(s.get("PT_retail", 0)) + 
                     self._map_acc_score(s.get("PT_GP", 0))) / 2
            features["Transport_Accessibility_Score"] = score
            
        if dz11 in self.income_cache:
            i = self.income_cache[dz11]
            features["avg_household_income"] = float(i.get('Weekly_Median_Income', 0)) * 52
            features["households"] = int(i.get("Households", 0))

        # 2. Demographics (Census 2022) - 2022 Based
        if dz22 in self.census_cache:
            c = self.census_cache[dz22]
            pop = c.get("pop", features.get("population", 0))
            features["population"] = pop
            
            # Normalize % to decimal
            white_count = c.get("white", 0)
            features["white"] = round(white_count / pop, 4) if pop > 0 else 0
            features["non-white"] = round((pop - white_count) / pop, 4) if pop > 0 else 0
            
            features["percent_muslim"] = round(c.get('muslim', 0) / pop, 4) if pop > 0 else 0
            
            t16 = c.get("t16", 1)
            features["ab"] = round(c.get("ab", 0) / t16, 4)
            features["c1/c2"] = round(c.get("c1c2", 0) / t16, 4)
            features["de"] = round(c.get("de", 0) / t16, 4)

        # 3. Transport (Distance in Miles)
        if lat and lng and self.stations:
            min_dist_km = float('inf')
            n_type, n_count = "N/A", 0
            for s in self.stations:
                d = self._haversine(lat, lng, s["Lat"], s["Lng"])
                if d < min_dist_km:
                    min_dist_km, n_type = d, s["Type"]
                if d <= 2.0: # 2km radius
                    n_count += 1
            
            # KM to Miles
            features["Distance_to_Nearest_Station"] = round(min_dist_km * 0.621371, 3)
            features["Nearby_Station_Count"] = n_count
            features["Nearest_Station_Type"] = n_type

        return features

    # --- Internal Helpers ---

    def _resolve_data_zones(self, pc_clean: str) -> tuple[Optional[str], Optional[str]]:
        """Maps postcode to 2022 and 2011 Data Zones."""
        with open(self.config.sspl_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row[0].replace(" ", "").upper() == pc_clean:
                    return row[12], row[13] # DZ2022, DZ2011
        return None, None

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * 
             math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _map_acc_score(self, time_mins):
        try:
            t = float(time_mins)
            if t < 5: return 9
            if t < 10: return 7
            if t < 15: return 5
            if t < 20: return 3
            return 1
        except: return 1

    def _load_stations(self):
        stations = []
        path = self.config.stations_path
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    stations.append({"Lat": float(r["Lat"]), "Lng": float(r["Lng"]), "Type": r["Type"]})
        return stations

    def _cache_census(self) -> Dict[str, Dict[str, Any]]:
        census = {}
        # Parsing UV201 (Ethnicity), UV205 (Religion), UV607 (Social Grade)
        # Assuming the standard filenames verified in previous steps.
        files = {
            "eth": "Table UV201 - Ethnic group.csv",
            "rel": "Table UV205 - Religion.csv",
            "sec": "Table UV607 - National Statistics Socio-economic Classification (NS-SeC).csv"
        }
        
        # Implementation matches the robust parsing logic we verified
        for key, fname in files.items():
            path = Path(self.config.census_dir) / fname
            if not path.exists(): continue
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for r in reader:
                    if not r or len(r) < 3: continue
                    dz = r[0].strip()
                    if not dz.startswith("S01"): continue
                    if dz not in census: census[dz] = {"ab":0, "c1c2":0, "de":0, "t16":0}
                    cat, val = r[1], int(r[2].replace("-","0").replace(",",""))
                    
                    if key == "eth":
                        if "All People" in cat: census[dz]["pop"] = val
                        if "White: Total" in cat: census[dz]["white"] = val
                    elif key == "rel":
                        if "Muslim" in cat: census[dz]["muslim"] = val
                    elif key == "sec":
                        if "All people aged 16 and over" in cat: census[dz]["t16"] = val
                        elif any(x in cat for x in ["L1:", "L2:", "L3:"]): census[dz]["ab"] += val
                        elif any(x in cat for x in ["L4:","L5:","L6:","L7:","L8:","L9:","L10:","L11:"]): census[dz]["c1c2"] += val
                        elif any(x in cat for x in ["L12:","L13:","L14.1:","L14.2:"]): census[dz]["de"] += val
        return census

    def _cache_simd(self):
        cache = {}
        if Path(self.config.indicators_path).exists():
            with open(self.config.indicators_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader: cache[r["Data_Zone"]] = r
        return cache

    def _cache_income(self):
        cache = {}
        if Path(self.config.income_path).exists():
            with open(self.config.income_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader: cache[r["Data_Zone"]] = r
        return cache
