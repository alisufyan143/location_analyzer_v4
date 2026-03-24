"""
Standardized resolver for Scottish location demographics and transport metrics.
Provides 1:1 parity with legacy scrapers but using official Scottish datasets
indexed in the local uk_master.db.
"""

import sqlite3
import math
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from location_analyzer.config import settings

logger = logging.getLogger(__name__)

class ScotlandResolver:
    """
    Critically resolves Scotland-specific features for the V3 ML pipeline.
    Uses local SQLite indices in uk_master.db (migrated from CSV).
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        """
        Initialize with an optional shared connection. 
        If not provided, it will open its own connection to uk_master.db.
        """
        self.config = settings.scotland
        self._external_conn = conn
        self._local_conn = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._external_conn:
            return self._external_conn
        if self._local_conn is None:
            # Common path for uk_master.db
            root = Path(__file__).resolve().parents[3]
            db_path = str(root / "data" / "uk_data" / "uk_master.db")
            if not os.path.exists(db_path):
                # Fallback to current settings if root-relative fails (unlikely in prod)
                db_path = str(Path(settings.paths.data_dir) / "uk_data" / "uk_master.db")
            
            self._local_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._local_conn.row_factory = sqlite3.Row
        return self._local_conn

    def is_scottish(self, postcode: str) -> bool:
        """Determines if a postcode belongs to Scotland via indexed SQLite lookup."""
        pc_clean = postcode.replace(" ", "").upper()
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM scot_postcode_index WHERE postcode_clean = ?", (pc_clean,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"SQLite error in is_scottish: {e}")
            return False

    def get_features(self, postcode: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
        """Resolves demographics and transport features using indexed SQLite queries."""
        pc_clean = postcode.replace(" ", "").upper()
        dzs = self._resolve_data_zones(pc_clean)
        if not dzs:
            logger.warning("Could not resolve Data Zones for Scottish postcode: %s", postcode)
            return {}

        dz22, dz11 = dzs["dz2022"], dzs["dz2011"]
        conn = self._get_conn()
        cursor = conn.cursor()
        
        features = {"postcode": postcode, "dz2011": dz11, "dz2022": dz22}

        # 1. Economic (SIMD Indicators & Income) - 2011 Data Zone based
        cursor.execute("SELECT * FROM scot_simd_indicators WHERE data_zone = ?", (dz11,))
        s = cursor.fetchone()
        if s:
            features["unemployment_rate"] = round(float(s['employment_rate']), 4)
            working_age = max(int(s["working_age_population"]), 1)
            emp_count = int(s["employment_count"])
            features["unemployed"] = round(emp_count / working_age, 4)
            features["working"] = round((working_age - emp_count) / working_age, 4)
            features["population"] = int(s["total_population"])
            
            # Transport Accessibility Score Mapping
            score = (self._map_acc_score(s["pt_retail"]) + self._map_acc_score(s["pt_gp"])) / 2
            features["Transport_Accessibility_Score"] = int(round(score))

        cursor.execute("SELECT * FROM scot_income WHERE data_zone = ?", (dz11,))
        i = cursor.fetchone()
        if i:
            features["avg_household_income"] = float(i['weekly_median_income']) * 52
            features["households"] = int(i["households"])

        # 2. Demographics (Census 2022) - 2022 Data Zone based
        cursor.execute("SELECT * FROM scot_census WHERE dz2022 = ?", (dz22,))
        c = cursor.fetchone()
        if c:
            pop = c["pop"] if c["pop"] > 0 else features.get("population", 1)
            pop = max(pop, 1)
            features["population"] = pop
            
            white_count = c["white"]
            features["white"] = round(white_count / pop, 4)
            features["non-white"] = round((pop - white_count) / pop, 4)
            features["percent_muslim"] = round(c['muslim'] / pop, 4)
            
            ab_raw, c1c2_raw, de_raw = c["ab"], c["c1c2"], c["de"]
            nssec_total = max(ab_raw + c1c2_raw + de_raw, 1)
            features["ab"] = round(ab_raw / nssec_total, 4)
            features["c1/c2"] = round(c1c2_raw / nssec_total, 4)
            features["de"] = round(de_raw / nssec_total, 4)

        # 3. Transport (Distance in Miles)
        if lat and lng:
            cursor.execute("SELECT lat, lng, type FROM scot_stations")
            stations = cursor.fetchall()
            if stations:
                min_dist_km = float('inf')
                n_type, n_count = "N/A", 0
                for st in stations:
                    d = self._haversine(lat, lng, st["lat"], st["lng"])
                    if d < min_dist_km:
                        min_dist_km, n_type = d, st["type"]
                    if d <= 2.0: # 2km radius count
                        n_count += 1
                
                features["Distance_to_Nearest_Station"] = round(min_dist_km * 0.621371, 3)
                features["Nearby_Station_Count"] = n_count
                features["Nearest_Station_Type"] = n_type

        return features

    def get_display_data(self, postcode: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
        """Formats rich demographics for dashboard UI using SQLite queries."""
        pc_clean = postcode.replace(" ", "").upper()
        dzs = self._resolve_data_zones(pc_clean)
        if not dzs: return {}
        dz22, dz11 = dzs["dz2022"], dzs["dz2011"]

        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scot_census WHERE dz2022 = ?", (dz22,))
        c = cursor.fetchone()
        cursor.execute("SELECT * FROM scot_simd_indicators WHERE data_zone = ?", (dz11,))
        s_data = cursor.fetchone()
        cursor.execute("SELECT * FROM scot_income WHERE data_zone = ?", (dz11,))
        i_data = cursor.fetchone()
        cursor.execute("SELECT country_decile FROM scot_simd_ranks WHERE data_zone = ?", (dz11,))
        rank_data = cursor.fetchone()

        if not c or not i_data: return {}
        pop = max(c["pop"], 1)
        
        display = {
            "postcode": postcode,
            "ethnicity": {
                "sections": {
                    "Ethnicity": [
                        {"name": "White British", "pct": round((c["white_british"]/pop)*100, 1)},
                        {"name": "White Irish",   "pct": round((c["white_irish"]/pop)*100, 1)},
                        {"name": "White",         "pct": round((c["white"]/pop)*100, 1)},
                        {"name": "Indian",        "pct": round((c["indian"]/pop)*100, 1)},
                        {"name": "Pakistani",     "pct": round((c["pakistani"]/pop)*100, 1)},
                        {"name": "Bangladeshi",   "pct": round((c["bangladeshi"]/pop)*100, 1)},
                        {"name": "Chinese",       "pct": round((c["chinese"]/pop)*100, 1)},
                        {"name": "Mixed",         "pct": round((c["mixed"]/pop)*100, 1)},
                        {"name": "Arab",          "pct": round((c["arab"]/pop)*100, 1)},
                    ],
                    "Religion": [
                        {"name": "Christian",         "pct": round((c["rel_christian"]/pop)*100, 1)},
                        {"name": "Muslim",            "pct": round((c["muslim"]/pop)*100, 1)},
                        {"name": "Hindu",             "pct": round((c["rel_hindu"]/pop)*100, 1)},
                        {"name": "Sikh",              "pct": round((c["rel_sikh"]/pop)*100, 1)},
                        {"name": "Jewish",            "pct": round((c["rel_jewish"]/pop)*100, 1)},
                        {"name": "Buddhist",          "pct": round((c["rel_buddhist"]/pop)*100, 1)},
                        {"name": "No Religion",       "pct": round((c["rel_none"]/pop)*100, 1)},
                        {"name": "Religion Not Stated","pct": round((c["rel_ns"]/pop)*100, 1)},
                    ],
                    "Age": [
                        {"name": "Aged 20 To 39", "pct": round((c["age_20_39"]/pop)*100, 1)},
                        {"name": "Aged 40 To 59", "pct": round((c["age_40_59"]/pop)*100, 1)},
                        {"name": "Aged 60 To 79", "pct": round((c["age_60_79"]/pop)*100, 1)},
                        {"name": "Aged 80",       "pct": round((c["age_80_plus"]/pop)*100, 1)},
                    ],
                    "Education (Highest Qualification)": [
                         {"name": "Degree Level or Above",  "pct": round((c["edu_degree"]/pop)*100, 1)},
                         {"name": "Further/Higher Education","pct": round((c["edu_fe"]/pop)*100, 1)},
                         {"name": "Upper School",           "pct": round((c["edu_upper"]/pop)*100, 1)},
                         {"name": "Lower School",           "pct": round((c["edu_lower"]/pop)*100, 1)},
                         {"name": "No Qualifications",      "pct": round((c["edu_none"]/pop)*100, 1)},
                    ]
                }
            },
            "affluence": {
                "income_pa": int(float(i_data['weekly_median_income']) * 52),
                "rating": str(rank_data['country_decile']) if rank_data else 'N/A'
            },
            "occupation": {
                "managerial and professional": round((c["ab"]/max(c["t16"],1))*100, 1),
                "intermediate occupations": round((c["occ_inter"]/max(c["t16"],1))*100, 1),
                "routine and manual": round((c["occ_routine"]/max(c["t16"],1))*100, 1),
                "never worked": round((c["occ_never"]/max(c["t16"],1))*100, 1),
                "full-time students": round((c["occ_student"]/max(c["t16"],1))*100, 1),
            },
            "transport": {
                "score": int((self._map_acc_score(s_data["pt_retail"]) + 
                             self._map_acc_score(s_data["pt_gp"])) / 2) if s_data else 1,
                "zone": "Scotland",
                "stations": []
            },
            "amenities": {"restaurants": [], "pubs": []}
        }

        if lat and lng:
            cursor.execute("SELECT lat, lng, type FROM scot_stations")
            stations = cursor.fetchall()
            nearby = []
            for st in stations:
                dist_mi = round(self._haversine(lat, lng, st["lat"], st["lng"]) * 0.621371, 2)
                if dist_mi <= 1.5:
                    nearby.append({"name": st["type"], "distance": dist_mi, "type": st["type"]})
            nearby = sorted(nearby, key=lambda x: x["distance"])[:10]
            display["transport"]["stations"] = nearby

        return display

    def _resolve_data_zones(self, pc_clean: str) -> Optional[Dict[str, str]]:
        """Maps postcode to 2022 and 2011 Data Zones via SQLite."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT dz2022, dz11 FROM scot_postcode_index WHERE postcode_clean = ?", (pc_clean,))
            row = cursor.fetchone()
            return {"dz2022": row["dz2022"], "dz2011": row["dz11"]} if row else None
        except sqlite3.Error:
            return None

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

    def __del__(self):
        if hasattr(self, '_local_conn') and self._local_conn:
            try:
                self._local_conn.close()
            except:
                pass

import os
