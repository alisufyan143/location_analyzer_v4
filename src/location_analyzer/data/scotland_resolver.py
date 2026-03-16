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
        self.simd_ranks_cache = None # Lazy load
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
        self._ensure_caches()

        features = {
            "postcode": postcode,
            "dz2011": dz11,
            "dz2022": dz22,
        }

        # 1. Economic (SIMD/Income) - 2011 Based
        if dz11 in self.simd_cache:
            s = self.simd_cache[dz11]
            features["unemployment_rate"] = round(float(s.get('Employment_rate', 0)), 4)
            # Convert raw counts to decimals (0.0-1.0) to match V3 model contract
            working_age = max(int(s.get("Working_age_population", 0)), 1)
            emp_count = int(s.get("Employment_count", 0))
            features["unemployed"] = round(emp_count / working_age, 4)
            features["working"] = round((working_age - emp_count) / working_age, 4)
            features["population"] = int(s.get("Total_population", 0))
            
            # Accessibility Score Mapping (cast to int for V3 OrdinalEncoder)
            score = (self._map_acc_score(s.get("PT_retail", 0)) + 
                     self._map_acc_score(s.get("PT_GP", 0))) / 2
            features["Transport_Accessibility_Score"] = int(round(score))
            
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
            
            # Normalize AB/C1C2/DE to sum to ~1.0 (use their own total, not t16)
            ab_raw = c.get("ab", 0)
            c1c2_raw = c.get("c1c2", 0)
            de_raw = c.get("de", 0)
            nssec_total = max(ab_raw + c1c2_raw + de_raw, 1)
            features["ab"] = round(ab_raw / nssec_total, 4)
            features["c1/c2"] = round(c1c2_raw / nssec_total, 4)
            features["de"] = round(de_raw / nssec_total, 4)

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

    def get_display_data(self, postcode: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
        """
        Formats rich demographics and transport data for the dashboard UI.
        Parity with CrystalRoofScraper output format.
        """
        pc_clean = postcode.replace(" ", "").upper()
        dz22, dz11 = self._resolve_data_zones(pc_clean)
        if not dz22 or not dz11: return {}

        self._ensure_caches()
        c = self.census_cache.get(dz22, {})
        s_data = self.simd_cache.get(dz11, {})
        i_data = self.income_cache.get(dz11, {})

        pop = c.get("pop", 1)
        
        # ── 1. Ethnicity / Religion / Age ───────────────────────────────────
        # Structure nested for Bokeh HTMLTemplateFormatter matches
        display = {
            "postcode": postcode,
            "ethnicity": {
                "sections": {
                    "Ethnicity": [
                        {"name": "White British", "pct": round((c.get("white_british",0)/pop)*100, 1)},
                        {"name": "White Irish",   "pct": round((c.get("white_irish",0)/pop)*100, 1)},
                        {"name": "White",         "pct": round((c.get("white",0)/pop)*100, 1)},
                        {"name": "Indian",        "pct": round((c.get("indian",0)/pop)*100, 1)},
                        {"name": "Pakistani",     "pct": round((c.get("pakistani",0)/pop)*100, 1)},
                        {"name": "Bangladeshi",   "pct": round((c.get("bangladeshi",0)/pop)*100, 1)},
                        {"name": "Chinese",       "pct": round((c.get("chinese",0)/pop)*100, 1)},
                        {"name": "Mixed",         "pct": round((c.get("mixed",0)/pop)*100, 1)},
                        {"name": "Arab",          "pct": round((c.get("arab",0)/pop)*100, 1)},
                    ],
                    "Religion": [
                        {"name": "Christian",         "pct": round((c.get("rel_christian",0)/pop)*100, 1)},
                        {"name": "Muslim",            "pct": round((c.get("muslim",0)/pop)*100, 1)},
                        {"name": "Hindu",             "pct": round((c.get("rel_hindu",0)/pop)*100, 1)},
                        {"name": "Sikh",              "pct": round((c.get("rel_sikh",0)/pop)*100, 1)},
                        {"name": "Jewish",            "pct": round((c.get("rel_jewish",0)/pop)*100, 1)},
                        {"name": "Buddhist",          "pct": round((c.get("rel_buddhist",0)/pop)*100, 1)},
                        {"name": "No Religion",       "pct": round((c.get("rel_none",0)/pop)*100, 1)},
                        {"name": "Religion Not Stated","pct": round((c.get("rel_ns",0)/pop)*100, 1)},
                    ],
                    "Age": [
                        {"name": "Aged 20 To 39", "pct": round((c.get("age_20_39",0)/pop)*100, 1)},
                        {"name": "Aged 40 To 59", "pct": round((c.get("age_40_59",0)/pop)*100, 1)},
                        {"name": "Aged 60 To 79", "pct": round((c.get("age_60_79",0)/pop)*100, 1)},
                        {"name": "Aged 80",       "pct": round((c.get("age_80_plus",0)/pop)*100, 1)},
                    ],
                    "Education (Highest Qualification)": [
                         {"name": "Degree Level or Above",  "pct": round((c.get("edu_degree",0)/pop)*100, 1)},
                         {"name": "Further/Higher Education","pct": round((c.get("edu_fe",0)/pop)*100, 1)},
                         {"name": "Upper School",           "pct": round((c.get("edu_upper",0)/pop)*100, 1)},
                         {"name": "Lower School",           "pct": round((c.get("edu_lower",0)/pop)*100, 1)},
                         {"name": "No Qualifications",      "pct": round((c.get("edu_none",0)/pop)*100, 1)},
                    ]
                }
            },
            # ── 2. Affluence ────────────────────────────────────────────────
            "affluence": {
                "income_pa": int(float(i_data.get('Weekly_Median_Income', 0)) * 52),
                "rating": self.simd_ranks_cache.get(dz11, {}).get('SIMD2020V2CountryDecile', 'N/A')
            },
            # ── 3. Occupation (NS-SeC Breakdown) ────────────────────────────
            "occupation": {
                "managerial and professional": round((c.get("ab",0)/max(c.get("t16",1),1))*100, 1),
                "intermediate occupations": round((c.get("occ_inter",0)/max(c.get("t16",1),1))*100, 1),
                "routine and manual": round((c.get("occ_routine",0)/max(c.get("t16",1),1))*100, 1),
                "never worked": round((c.get("occ_never",0)/max(c.get("t16",1),1))*100, 1),
                "full-time students": round((c.get("occ_student",0)/max(c.get("t16",1),1))*100, 1),
            },
            # ── 4. Transport ────────────────────────────────────────────────
            "transport": {
                "score": int((self._map_acc_score(s_data.get("PT_retail", 0)) + 
                             self._map_acc_score(s_data.get("PT_GP", 0))) / 2),
                "zone": "Scotland",
                "stations": []
            },
            "amenities": {"restaurants": [], "pubs": []} # To be merged by Pipeline (Hybrid)
        }

        # Detailed station list
        if lat and lng and self.stations:
            nearby = []
            for s in self.stations:
                dist_mi = round(self._haversine(lat, lng, s["Lat"], s["Lng"]) * 0.621371, 2)
                if dist_mi <= 1.5: # 1.5 mile radius for display
                    nearby.append({"name": s["Type"], "distance": dist_mi, "type": s["Type"]})
            
            nearby = sorted(nearby, key=lambda x: x["distance"])[:10]
            display["transport"]["stations"] = nearby

        return display

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

    def _ensure_caches(self):
        if self.census_cache is None: self.census_cache = self._cache_census()
        if self.simd_cache is None: self.simd_cache = self._cache_simd()
        if self.simd_ranks_cache is None: self.simd_ranks_cache = self._cache_simd_ranks()
        if self.income_cache is None: self.income_cache = self._cache_income()

    def _cache_simd_ranks(self) -> Dict[str, Dict[str, Any]]:
        cache = {}
        if Path(self.config.ranks_path).exists():
            with open(self.config.ranks_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader: cache[r["DataZone"]] = r
        return cache

    def _cache_census(self) -> Dict[str, Dict[str, Any]]:
        census = {}
        # Parsing UV201 (Ethnicity), UV205 (Religion), UV607 (Social Grade), UV102b (Age), UV501 (Edu)
        files = {
            "eth": "Table UV201 - Ethnic group.csv",
            "rel": "Table UV205 - Religion.csv",
            "sec": "Table UV607 - National Statistics Socio-economic Classification (NS-SeC).csv",
            "age": "Table UV102b - Age (20) by sex.csv",
            "edu": "Table UV501 - Highest level of qualification.csv",
        }
        
        for key, fname in files.items():
            path = Path(self.config.census_dir) / fname
            if not path.exists(): continue
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for r in reader:
                    if not r or len(r) < 3: continue
                    dz = r[0].strip()
                    if not dz.startswith("S01"): continue
                    
                    if dz not in census: 
                        census[dz] = {
                            "ab":0, "c1c2":0, "de":0, "t16":0, 
                            "white":0, "white_british":0, "white_irish":0,
                            "indian":0, "pakistani":0, "bangladeshi":0, "chinese":0, "mixed":0, "arab":0,
                            "rel_christian":0, "rel_buddhist":0, "rel_hindu":0, "rel_jewish":0, "muslim":0, "rel_sikh":0, "rel_none":0, "rel_ns":0,
                            "age_20_39":0, "age_40_59":0, "age_60_79":0, "age_80_plus":0,
                            "edu_degree":0, "edu_fe":0, "edu_upper":0, "edu_lower":0, "edu_none":0,
                            "occ_inter":0, "occ_routine":0, "occ_never":0, "occ_student":0
                        }
                    
                    cat, val_str = r[1].strip(), r[-1].replace("-","0").replace(",","")
                    try: val = int(val_str)
                    except: val = 0
                    
                    # ── Ethnicity ── (UV201)
                    if key == "eth":
                        if "All People" in cat: census[dz]["pop"] = val
                        elif cat == "White: Total": census[dz]["white"] = val
                        elif any(x in cat for x in ["White: Scottish", "White: Other British"]): census[dz]["white_british"] += val
                        elif cat == "White: Irish": census[dz]["white_irish"] = val
                        elif "Indian" in cat:      census[dz]["indian"] = val
                        elif "Pakistani" in cat:   census[dz]["pakistani"] = val
                        elif "Bangladeshi" in cat: census[dz]["bangladeshi"] = val
                        elif "Chinese" in cat:     census[dz]["chinese"] = val
                        elif "Mixed" in cat:       census[dz]["mixed"] = val
                        elif "Arab" in cat:        census[dz]["arab"] = val
                    
                    # ── Religion ── (UV205)
                    elif key == "rel":
                        if cat == "Christian": census[dz]["rel_christian"] = val
                        elif cat == "Buddhist": census[dz]["rel_buddhist"] = val
                        elif cat == "Hindu": census[dz]["rel_hindu"] = val
                        elif cat == "Jewish": census[dz]["rel_jewish"] = val
                        elif cat == "Muslim": census[dz]["muslim"] = val
                        elif cat == "Sikh": census[dz]["rel_sikh"] = val
                        elif cat == "No religion": census[dz]["rel_none"] = val
                        elif cat == "Not answered": census[dz]["rel_ns"] = val
                    
                    # ── NS-SeC (Occupation/Social Grade) ── (UV607)
                    elif key == "sec":
                        # L-categories map to AB/C1C2/DE and also dashboard groups
                        if "All people aged 16 and over" in cat: census[dz]["t16"] = val
                        elif any(x in cat for x in ["L1:", "L2:", "L3:"]): census[dz]["ab"] += val
                        elif any(x in cat for x in ["L4:","L5:","L6:"]):   census[dz]["ab"] += val # England mapping includes L4-L6 in AB
                        elif "L7 Intermediate" in cat: census[dz]["occ_inter"] += val; census[dz]["c1c2"] += val
                        elif any(x in cat for x in ["L8:","L9:","L10:","L11:"]): census[dz]["c1c2"] += val
                        elif any(x in cat for x in ["L12:","L13:"]): census[dz]["occ_routine"] += val; census[dz]["de"] += val
                        elif "L14" in cat: census[dz]["occ_never"] += val; census[dz]["de"] += val
                        elif "L15" in cat: census[dz]["occ_student"] += val
                    
                    # ── Age ── (UV102b)
                    elif key == "age":
                        # We use "All people" gender filter implicitly by checking first row matches
                        if r[2] != "All people": continue
                        if any(x in cat for x in ["20 - 24", "25 - 29", "30 - 34", "35 - 39"]): census[dz]["age_20_39"] += val
                        elif any(x in cat for x in ["40 - 44", "45 - 49", "50 - 54", "55 - 59"]): census[dz]["age_40_59"] += val
                        elif any(x in cat for x in ["60 - 64", "65 - 69", "70 - 74", "75 - 79"]): census[dz]["age_60_79"] += val
                        elif any(x in cat for x in ["80", "85", "90"]): census[dz]["age_80_plus"] += val

                    # ── Education ── (UV501)
                    elif key == "edu":
                        if "Degree level" in cat: census[dz]["edu_degree"] = val
                        elif "Further Education" in cat: census[dz]["edu_fe"] = val
                        elif "Upper school" in cat: census[dz]["edu_upper"] = val
                        elif "Lower school" in cat: census[dz]["edu_lower"] = val
                        elif "No qualifications" in cat: census[dz]["edu_none"] = val

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
