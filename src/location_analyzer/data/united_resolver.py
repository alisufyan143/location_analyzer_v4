"""
United Resolver: The central hub for UK-wide high-fidelity offline lookups.
Bypasses standard scrapers by querying a local Master SQLite database for England/Wales,
and routing to ScotlandResolver for Scottish postcodes.

Feature Parity Contract (V3 Model):
  - All percentages returned as decimals (0.0–1.0)
  - Distances in miles
  - Transport score as integer (1–9)
  - Feature names match exactly: white, non-white, c1/c2, percent_muslim, etc.
"""

import sqlite3
import os
import logging
import math
from pathlib import Path
from typing import Dict, Any, Optional

from location_analyzer.config import settings
from location_analyzer.data.scotland_resolver import ScotlandResolver

logger = logging.getLogger(__name__)

# NaPTAN stop_type → human-readable type (matching CrystalRoof/training data)
STOP_TYPE_MAP = {
    "BCT": "Bus",         # Bus/Coach/Tram stop
    "BCS": "Bus",         # Bus/Coach stop
    "BCE": "Bus",         # Bus/Coach entrance
    "BST": "Bus",         # Bus stop
    "PLT": "Underground", # Platform (Tube/Metro)
    "MET": "Underground", # Metro/Tram
    "RLY": "Rail",        # Railway station
    "RSE": "Rail",        # Railway station entrance
    "FER": "Ferry",       # Ferry terminal
    "FBT": "Ferry",       # Ferry berth
    "AIR": "Air",         # Airport
    "GAT": "Air",         # Airport gate
    "TMU": "Tram",        # Tram/Metro/Underground
    "TXR": "Taxi",        # Taxi rank
}


class UnitedResolver:
    """
    Consolidates UK demographic and transport resolution.
    Reliably routes requests based on official GSS country codes.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        else:
            root = Path(__file__).resolve().parents[3]
            self.db_path = str(root / "data" / "uk_data" / "uk_master.db")

        self._conn = None
        self._scotland_resolver = None

    def _get_conn(self):
        """Lazy database connection."""
        if self._conn is None:
            if not os.path.exists(self.db_path):
                logger.error(f"Master UK database not found at {self.db_path}")
                return None
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _get_scotland_resolver(self):
        """Lazy load Scotland resolver with shared connection."""
        if self._scotland_resolver is None:
            self._scotland_resolver = ScotlandResolver(conn=self._get_conn())
        return self._scotland_resolver

    def get_features(self, postcode: str) -> Dict[str, Any]:
        """
        Main entry point for ML feature resolution.
        Returns features matching the exact V3 model contract.
        """
        pc_clean = postcode.replace(" ", "").upper()
        conn = self._get_conn()
        if not conn:
            return {}

        try:
            cursor = conn.cursor()

            # 1. Resolve Geography
            cursor.execute("SELECT * FROM postcode_index WHERE postcode_clean = ?", (pc_clean,))
            geo = cursor.fetchone()

            if not geo:
                logger.warning(f"Postcode {postcode} not found in UK Master Index.")
                return {}

            lat, lon = geo['latitude'], geo['longitude']
            outercode = postcode.strip().split()[0] if " " in postcode else postcode[:len(postcode)-3].strip()

            # 2. Regional Routing (GSS Code)
            lad_code = geo['lad_code']
            if lad_code:
                if lad_code.startswith('S'):
                    logger.info(f"Routing {postcode} to ScotlandResolver (LAD: {lad_code})")
                    scot_features = self._get_scotland_resolver().get_features(postcode, lat, lon)
                    if scot_features:
                        scot_features["outercode"] = outercode
                        scot_features["lat"] = lat
                        scot_features["lng"] = lon
                    return scot_features
                
                if lad_code.startswith('N'):
                    logger.info(f"Routing {postcode} to NI Offline Logic (LAD: {lad_code})")
                    return self._resolve_ni_features(geo, postcode, outercode, lat, lon, cursor)

            # 3. England/Wales Resolution (Master DB joins)
            oa = geo['oa21']
            lsoa = geo['lsoa21']
            msoa = geo['msoa21']

            # Detailed Census + IMD + Income Join
            query = """
                SELECT
                    c.population, c.households,
                    c.white, c.non_white, c.percent_muslim,
                    c.unemployment_rate, c.working, c.unemployed,
                    c.ab, c.c1c2, c.de,
                    i.income_score, i.employment_score,
                    mi.total_annual_income as avg_household_income
                FROM census_data c
                LEFT JOIN imd_data i ON i.lsoa_code = ?
                LEFT JOIN msoa_income mi ON mi.msoa_code = ?
                WHERE c.oa_code = ?
            """
            cursor.execute(query, (lsoa, msoa, oa))
            data = cursor.fetchone()

            if not data:
                logger.warning(f"No demographic coverage for OA {oa} (Postcode: {postcode})")
                return {}

            # 4. Assemble Feature Dict (exact V3 contract)
            features = {
                "postcode": postcode,
                "outercode": outercode,
                "msoa": msoa,
                "lat": lat,
                "lng": lon,
                "population": data['population'],
                "households": data['households'],
                "avg_household_income": data['avg_household_income'],
                "white": data['white'],
                "non-white": data['non_white'],
                "percent_muslim": data['percent_muslim'],
                "unemployment_rate": data['unemployment_rate'],
                "working": data['working'],
                "unemployed": data['unemployed'],
                "ab": data['ab'],
                "c1/c2": data['c1c2'],
                "de": data['de'],
            }

            # 5. Transport Resolution
            transport = self._resolve_nearest_transport(lat, lon, cursor)
            features.update(transport)

            return features

        except Exception as e:
            logger.error(f"Failed to resolve features for {postcode}: {e}")
            return {}

    def get_display_data(self, postcode: str) -> Dict[str, Any]:
        """
        Build the _display dict for frontend rendering.
        Matches the format that ResultsPanel.jsx and routes.py/export-plot expect.
        """
        pc_clean = postcode.replace(" ", "").upper()
        conn = self._get_conn()
        if not conn:
            return {}

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM postcode_index WHERE postcode_clean = ?", (pc_clean,))
            geo = cursor.fetchone()
            if not geo:
                return {}

            lat, lon = geo['latitude'], geo['longitude']
            lad_code = geo['lad_code']

            # Scotland → delegate to ScotlandResolver's display_data + merge offline amenities
            if lad_code and lad_code.startswith('S'):
                display = self._get_scotland_resolver().get_display_data(postcode, lat=lat, lng=lon)
                display["amenities"] = self._get_nearby_amenities(lat, lon, cursor)
                return display

            # NI → build from ni_census_data
            if lad_code and lad_code.startswith('N'):
                return self._build_ni_display(geo, lat, lon, cursor)

            # England/Wales → build from census_data
            return self._build_ew_display(geo, lat, lon, cursor)

        except Exception as e:
            logger.error(f"Failed to build display data for {postcode}: {e}")
            return {}

    def _build_ew_display(self, geo, lat, lon, cursor) -> Dict[str, Any]:
        """Build display data for England/Wales from census_data + imd_data + msoa_income."""
        oa = geo['oa21']
        msoa = geo['msoa21']
        lsoa = geo['lsoa21']

        # Fetch census row
        cursor.execute("SELECT * FROM census_data WHERE oa_code = ?", (oa,))
        census = cursor.fetchone()
        if not census:
            return {}

        pop = census['population'] or 1

        # Fetch income
        cursor.execute("SELECT total_annual_income FROM msoa_income WHERE msoa_code = ?", (msoa,))
        income_row = cursor.fetchone()
        income_pa = int(income_row['total_annual_income']) if income_row else 0

        # Transport
        transport_info = self._resolve_nearest_transport(lat, lon, cursor)

        display = {
            "ethnicity": {
                "sections": {
                    "Ethnicity": [
                        {"name": "White", "pct": round(census['white'] * 100, 1) if census['white'] <= 1 else round(census['white'] / pop * 100, 1)},
                        {"name": "Non-White", "pct": round(census['non_white'] * 100, 1) if census['non_white'] <= 1 else round(census['non_white'] / pop * 100, 1)},
                    ],
                    "Religion": [
                        {"name": "Muslim", "pct": round(census['percent_muslim'] * 100, 1) if census['percent_muslim'] is not None else 0},
                    ],
                }
            },
            "affluence": {
                "income_pa": income_pa,
                "rating": self._calculate_affluence_rating(income_pa, lsoa, cursor),
            },
            "transport": {
                "score": transport_info.get("Transport_Accessibility_Score", 1),
                "zone": "N/A",
                "stations": [],
            },
            "occupation": self._get_occupation_data(oa, cursor),
            "amenities": self._get_nearby_amenities(lat, lon, cursor),
        }
        return display

    def _build_ni_display(self, geo, lat, lon, cursor) -> Dict[str, Any]:
        """Build display data for Northern Ireland from ni_census_data."""
        oa = geo['oa21']  # DZ code stored here

        cursor.execute("SELECT * FROM ni_census_data WHERE dz_code = ?", (oa,))
        data = cursor.fetchone()
        if not data:
            return {}

        pop = data['population'] or 1
        rel_total = data['total_rel'] or 1
        sg_total = (data['ab'] or 0) + (data['c1c2'] or 0) + (data['de'] or 0) or 1

        # Income proxy
        income_proxy = ((data['ab'] or 0) * 48000 + (data['c1c2'] or 0) * 32000 + (data['de'] or 0) * 22000) / sg_total

        transport_info = self._resolve_nearest_transport(lat, lon, cursor)

        display = {
            "ethnicity": {
                "sections": {
                    "Ethnicity": [
                        {"name": "White", "pct": round((data['white'] or 0) / pop * 100, 1)},
                        {"name": "Non-White", "pct": round((data['non_white'] or 0) / pop * 100, 1)},
                    ],
                    "Religion": [
                        {"name": "Muslim", "pct": round((data['muslim'] or 0) / rel_total * 100, 1)},
                    ],
                }
            },
            "affluence": {
                "income_pa": int(round(income_proxy, 0)),
                "rating": self._calculate_affluence_rating(income_proxy, None, cursor),
            },
            "transport": {
                "score": transport_info.get("Transport_Accessibility_Score", 1),
                "zone": "N/A",
                "stations": [],
            },
            "occupation": self._get_ni_occupation_data(oa, data, cursor),
            "amenities": self._get_nearby_amenities(lat, lon, cursor),
        }
        return display

    def _resolve_ni_features(self, geo: sqlite3.Row, postcode: str, outercode: str, lat: float, lon: float, cursor: sqlite3.Cursor) -> Dict[str, Any]:
        """Specific logic for Northern Ireland Data Zone (DZ) resolution."""
        oa = geo['oa21']  # Data Zone code is stored in oa21 column
        
        query = """
            SELECT * FROM ni_census_data WHERE dz_code = ?
        """
        cursor.execute(query, (oa,))
        data = cursor.fetchone()
        
        if not data:
            logger.warning(f"No NI demographic coverage for Data Zone {oa}")
            return {}

        pop = data['population'] or 1
        rel_total = data['total_rel'] or 1
        eco_total = data['total_eco'] or 1
        sg_total = (data['ab'] or 0) + (data['c1c2'] or 0) + (data['de'] or 0) or 1

        # Income Proxy: Weighted Social Grade (Heuristic based on UK averages for NI)
        # AB: ~48k, C1C2: ~32k, DE: ~22k
        income_proxy = ((data['ab'] or 0) * 48000 + (data['c1c2'] or 0) * 32000 + (data['de'] or 0) * 22000) / sg_total

        features = {
            "postcode": postcode,
            "outercode": outercode,
            "msoa": geo['msoa21'], # SDZ code
            "lat": lat,
            "lng": lon,
            "population": pop,
            "households": data['households'],
            "avg_household_income": round(income_proxy, 0),
            "white": round((data['white'] or 0) / pop, 4),
            "non-white": round((data['non_white'] or 0) / pop, 4),
            "percent_muslim": round((data['muslim'] or 0) / rel_total, 4),
            "unemployment_rate": round((data['unemployed'] or 0) / eco_total, 4),
            "working": round((data['working'] or 0) / pop, 4),
            "unemployed": round((data['unemployed'] or 0) / pop, 4),
            "ab": round((data['ab'] or 0) / sg_total, 4),
            "c1/c2": round((data['c1c2'] or 0) / sg_total, 4),
            "de": round((data['de'] or 0) / sg_total, 4),
        }

        # Transport
        transport = self._resolve_nearest_transport(lat, lon, cursor)
        features.update(transport)
        
        return features

    def _resolve_nearest_transport(self, lat: float, lon: float, cursor: sqlite3.Cursor) -> Dict[str, Any]:
        """Spatial search for the nearest transport node."""
        query = """
            SELECT
                common_name, stop_type, latitude, longitude,
                ((latitude - ?) * (latitude - ?) + (longitude - ?) * (longitude - ?)) as dist_sq
            FROM transport_nodes
            ORDER BY dist_sq ASC
            LIMIT 1
        """
        cursor.execute(query, (lat, lat, lon, lon))
        node = cursor.fetchone()

        if not node:
            return {
                "Distance_to_Nearest_Station": 0.0,
                "Nearby_Station_Count": 0,
                "Nearest_Station_Type": "N/A",
                "Transport_Accessibility_Score": 1,
            }

        dist_mi = self._haversine_miles(lat, lon, node['latitude'], node['longitude'])

        # Count stations within ~1.5 mile bounding box
        cursor.execute("""
            SELECT COUNT(*) FROM transport_nodes
            WHERE latitude BETWEEN ? AND ?
            AND longitude BETWEEN ? AND ?
        """, (lat - 0.02, lat + 0.02, lon - 0.03, lon + 0.03))
        nearby_count = cursor.fetchone()[0]

        # Map NaPTAN code to human-readable type
        raw_type = node['stop_type'] or "Unknown"
        mapped_type = STOP_TYPE_MAP.get(raw_type, raw_type)

        return {
            "Distance_to_Nearest_Station": round(dist_mi, 3),
            "Nearby_Station_Count": nearby_count,
            "Nearest_Station_Type": mapped_type,
            "Transport_Accessibility_Score": self._calculate_transport_score(dist_mi),
        }

    def _haversine_miles(self, lat1, lon1, lat2, lon2):
        R = 3958.8
        dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _calculate_transport_score(self, distance_mi: float) -> int:
        """Heuristic score (1–9) matching CrystalRoof/V3 expectations."""
        if distance_mi < 0.1:  return 9
        if distance_mi < 0.25: return 8
        if distance_mi < 0.5:  return 7
        if distance_mi < 0.75: return 6
        if distance_mi < 1.0:  return 4
        return 1

    def _get_occupation_data(self, geo_code: str, cursor: sqlite3.Cursor) -> Dict[str, Any]:
        """Fetches occupation breakdown from the local census_occupation table (E&W)."""
        cursor.execute("SELECT * FROM census_occupation WHERE geo_code = ?", (geo_code,))
        row = cursor.fetchone()
        if not row:
            return {}

        return {
            "sections": {
                "Employment Type": [
                    {"name": "Managerial & Professional", "pct": round(row['managerial_professional'], 1)},
                    {"name": "Intermediate Occupations", "pct": round(row['intermediate'], 1)},
                    {"name": "Routine & Manual", "pct": round(row['routine_manual'], 1)},
                ],
                "Economic Activity": [
                    {"name": "Full-time Students", "pct": round(row['full_time_students'], 1)},
                    {"name": "Unemployed / Never Worked", "pct": round(row['never_worked'], 1)},
                ]
            }
        }

    def _get_ni_occupation_data(self, dz_code: str, ni_census_row: sqlite3.Row, cursor: sqlite3.Cursor) -> Dict[str, Any]:
        """Merges NISRA Social Grade with ingested student/unemployment counts for NI."""
        cursor.execute("SELECT * FROM census_occupation WHERE geo_code = ?", (dz_code,))
        row = cursor.fetchone()
        
        # Calculate percentages from raw counts in ni_census_row for social grade
        # These columns exist: ab, c1c2, de (raw counts from our audit)
        sg_total = (ni_census_row['ab'] or 0) + (ni_census_row['c1c2'] or 0) + (ni_census_row['de'] or 0) or 1
        
        # Get student/unemployed % from census_occupation (already pct)
        ft_students = row['full_time_students'] if row else 0
        never_worked = row['never_worked'] if row else 0

        return {
            "sections": {
                "Social Grade (NI)": [
                    {"name": "AB (Managerial/Prof)", "pct": round((ni_census_row['ab'] or 0) / sg_total * 100, 1)},
                    {"name": "C1C2 (Intermediate/Skilled)", "pct": round((ni_census_row['c1c2'] or 0) / sg_total * 100, 1)},
                    {"name": "DE (Semi-Skilled/Unskilled)", "pct": round((ni_census_row['de'] or 0) / sg_total * 100, 1)},
                ],
                "Economic Activity": [
                    {"name": "Full-time Students", "pct": round(ft_students, 1)},
                    {"name": "Unemployed / Never Worked", "pct": round(never_worked, 1)},
                ]
            }
        }

    def _get_nearby_amenities(self, lat: float, lon: float, cursor: sqlite3.Cursor) -> Dict[str, Any]:
        """Spatial lookup for restaurants and pubs within ~1km."""
        # 1km bounding box approx (0.01 deg lat, 0.02 deg lon)
        query = """
            SELECT name, type, latitude, longitude
            FROM amenities
            WHERE latitude BETWEEN ? AND ?
            AND longitude BETWEEN ? AND ?
        """
        cursor.execute(query, (lat - 0.01, lat + 0.01, lon - 0.015, lon + 0.015))
        rows = cursor.fetchall()

        results = {"restaurants": [], "pubs": []}
        
        for row in rows:
            dist_mi = self._haversine_miles(lat, lon, row['latitude'], row['longitude'])
            if dist_mi > 0.62: # 1km = 0.62 miles
                continue
                
            item = {
                "name": row['name'],
                "type": row['type'],
                "distance": round(dist_mi, 2)
            }
            
            # Map types to buckets expected by frontend
            if row['type'] in ('restaurant', 'fast_food', 'cafe'):
                results['restaurants'].append(item)
            elif row['type'] in ('pub', 'bar'):
                results['pubs'].append(item)

        # Sort by distance and limit to top 15 each
        results['restaurants'] = sorted(results['restaurants'], key=lambda x: x['distance'])[:15]
        results['pubs'] = sorted(results['pubs'], key=lambda x: x['distance'])[:15]

        return results

    def _calculate_affluence_rating(self, income_pa: float, lsoa: Optional[str], cursor: sqlite3.Cursor) -> str:
        """Calculates a 1-10 affluence rating based on UK deciles."""
        # 1. Income Decile (Primary)
        # Thresholds based on MSOA distribution: 25k - 128k (Avg 55k)
        if income_pa < 32000:   i_decile = 1
        elif income_pa < 38000: i_decile = 2
        elif income_pa < 44000: i_decile = 3
        elif income_pa < 50000: i_decile = 4
        elif income_pa < 56000: i_decile = 5
        elif income_pa < 65000: i_decile = 6
        elif income_pa < 75000: i_decile = 7
        elif income_pa < 90000: i_decile = 8
        elif income_pa < 110000: i_decile = 9
        else: i_decile = 10

        # 2. IMD Income Score Decile (Secondary - E&W only)
        if lsoa:
            cursor.execute("SELECT income_score FROM imd_data WHERE lsoa_code = ?", (lsoa,))
            row = cursor.fetchone()
            if row and row['income_score'] is not None:
                s = row['income_score']
                # IMD Income Score (0.003 - 0.61, Avg 0.13), Lower is more affluent
                if s < 0.02:   s_decile = 10
                elif s < 0.04: s_decile = 9
                elif s < 0.06: s_decile = 8
                elif s < 0.08: s_decile = 7
                elif s < 0.12: s_decile = 6
                elif s < 0.18: s_decile = 5
                elif s < 0.25: s_decile = 4
                elif s < 0.35: s_decile = 3
                elif s < 0.45: s_decile = 2
                else: s_decile = 1
                
                # Blend (70% income, 30% IMD)
                final_decile = int(round(i_decile * 0.7 + s_decile * 0.3))
                return str(max(1, min(10, final_decile)))

        return str(i_decile)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
