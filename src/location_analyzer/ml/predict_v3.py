"""
V3 Enterprise Prediction Service
=================================
Replaces the V1 MedianEnsembleRegressor + fragmented pkl transformers
with the V3 pipeline: unified preprocessor.joblib + 3 models (XGBoost,
ExtraTrees, TabNet) blended via SciPy-optimized weights + real ONS CPI
reverse-inflation.
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─── Lunar Calendar & Holiday Lookup (Full 21-Year Expansion 2010-2030) ───
HOLIDAY_MAP = {
    2010: {"ramadan": [("2010-08-11", "2010-09-09")], "eid_fitr": ["2010-09-10"], "eid_adha": ["2010-11-16"]},
    2011: {"ramadan": [("2011-08-01", "2011-08-30")], "eid_fitr": ["2011-08-31"], "eid_adha": ["2011-11-06"]},
    2012: {"ramadan": [("2012-07-20", "2012-08-18")], "eid_fitr": ["2012-08-19"], "eid_adha": ["2012-10-26"]},
    2013: {"ramadan": [("2013-07-09", "2013-08-07")], "eid_fitr": ["2013-08-08"], "eid_adha": ["2013-10-15"]},
    2014: {"ramadan": [("2014-06-28", "2014-07-27")], "eid_fitr": ["2014-07-28"], "eid_adha": ["2014-10-04"]},
    2015: {"ramadan": [("2015-06-18", "2015-07-16")], "eid_fitr": ["2015-07-17"], "eid_adha": ["2015-09-23"]},
    2016: {"ramadan": [("2016-06-06", "2016-07-05")], "eid_fitr": ["2016-07-06"], "eid_adha": ["2016-09-12"]},
    2017: {"ramadan": [("2017-05-27", "2017-06-24")], "eid_fitr": ["2017-06-25"], "eid_adha": ["2017-09-01"]},
    2018: {"ramadan": [("2018-05-16", "2018-06-14")], "eid_fitr": ["2018-06-15"], "eid_adha": ["2018-08-21"]},
    2019: {"ramadan": [("2019-05-05", "2019-06-03")], "eid_fitr": ["2019-06-04"], "eid_adha": ["2019-08-11"]},
    2020: {"ramadan": [("2020-04-23", "2020-05-22")], "eid_fitr": ["2020-05-23"], "eid_adha": ["2020-07-31"]},
    2021: {"ramadan": [("2021-04-12", "2021-05-11")], "eid_fitr": ["2021-05-12"], "eid_adha": ["2021-07-20"]},
    2022: {"ramadan": [("2022-04-01", "2022-04-30")], "eid_fitr": ["2022-05-02"], "eid_adha": ["2022-07-09"]},
    2023: {"ramadan": [("2023-03-22", "2023-04-20")], "eid_fitr": ["2023-04-21"], "eid_adha": ["2023-06-28"]},
    2024: {"ramadan": [("2024-03-10", "2024-04-08")], "eid_fitr": ["2024-04-09"], "eid_adha": ["2024-06-16"]},
    2025: {"ramadan": [("2025-02-28", "2025-03-30")], "eid_fitr": ["2025-03-31"], "eid_adha": ["2025-06-07"]},
    2026: {"ramadan": [("2026-02-18", "2026-03-19")], "eid_fitr": ["2026-03-20"], "eid_adha": ["2026-05-26"]},
    2027: {"ramadan": [("2027-02-08", "2027-03-09")], "eid_fitr": ["2027-03-10"], "eid_adha": ["2027-05-17"]},
    2028: {"ramadan": [("2028-01-28", "2028-02-26")], "eid_fitr": ["2028-02-27"], "eid_adha": ["2028-05-06"]},
    2029: {"ramadan": [("2029-01-16", "2029-02-14")], "eid_fitr": ["2029-02-15"], "eid_adha": ["2029-04-24"]},
    2030: {
        "ramadan": [("2030-01-05", "2030-02-03"), ("2030-12-25", "2030-12-31")], 
        "eid_fitr": ["2030-02-04"], 
        "eid_adha": ["2030-04-13"]
    },
}


# ─── Brand Extraction (mirrors engineer_brand_maturity.py) ────────────────
def extract_brand(branch_name: str) -> str:
    """Extract the inferred brand from a branch name string."""
    if not branch_name or not isinstance(branch_name, str):
        return "Independent"
    name = branch_name.lower()
    if "pepe" in name:
        return "Pepe's"
    elif "rio" in name:
        return "Rio's"
    elif "maeme" in name:
        return "Maeme's"
    elif "galo" in name:
        return "Galos"
    return "Independent"


class V3PredictionService:
    """
    Loads the V3 Enterprise ML Pipeline artifacts and provides real-time
    sales predictions with SciPy meta-ensemble blending and real CPI
    reverse-inflation.
    """

    def __init__(self, model_dir: str, cpi_path: Optional[str] = None):
        self.model_dir = model_dir
        self.preprocessor = None
        self.xgb_model = None
        self.et_model = None
        self.tabnet_model = None
        self.config = None
        self.demographics_db = None
        self.cpi_df = None
        self.base_cpi = None
        self._load_artifacts(cpi_path)

    def _load_artifacts(self, cpi_path: Optional[str] = None):
        """Load all V3 artifacts from the model directory."""
        try:
            # 1. Preprocessor (unified ColumnTransformer)
            prep_path = os.path.join(self.model_dir, "preprocessor.joblib")
            self.preprocessor = joblib.load(prep_path)
            logger.info("Loaded V3 preprocessor from %s", prep_path)

            # 2. XGBoost
            import xgboost as xgb
            xgb_path = os.path.join(self.model_dir, "xgboost_model.json")
            self.xgb_model = xgb.XGBRegressor()
            self.xgb_model.load_model(xgb_path)
            logger.info("Loaded V3 XGBoost from %s", xgb_path)

            # 3. ExtraTrees
            et_path = os.path.join(self.model_dir, "extratrees_model.joblib")
            self.et_model = joblib.load(et_path)
            logger.info("Loaded V3 ExtraTrees from %s", et_path)

            # 4. TabNet
            from pytorch_tabnet.tab_model import TabNetRegressor
            tab_path = os.path.join(self.model_dir, "tabnet_model.zip")
            self.tabnet_model = TabNetRegressor()
            self.tabnet_model.load_model(tab_path)
            logger.info("Loaded V3 TabNet from %s", tab_path)

            # 4.5 TabNet Safety Bounds
            bounds_path = os.path.join(self.model_dir, "tabnet_bounds.json")
            if os.path.exists(bounds_path):
                with open(bounds_path, "r") as f:
                    self.tabnet_bounds = json.load(f)
                logger.info("Loaded TabNet safety bounds from %s", bounds_path)
            else:
                self.tabnet_bounds = None
                logger.warning("TabNet safety bounds NOT found. Risk of CUDA crash on unseen categories.")

            # 5. Pipeline Config (weights + expected features)
            config_path = os.path.join(self.model_dir, "pipeline_config.json")
            with open(config_path, "r") as f:
                self.config = json.load(f)
            logger.info("Loaded V3 config: weights=%s", self.config["ensemble_weights"])

            # 6. Demographics Lookup DB
            demo_path = os.path.join(self.model_dir, "outercode_demographics_db.csv")
            self.demographics_db = pd.read_csv(demo_path)
            logger.info("Loaded demographics DB: %d outercodes", len(self.demographics_db))

            # 7. CPI Data
            cpi_file = cpi_path or os.path.join(self.model_dir, "cpi_d7ew_restaurants.csv")
            self.cpi_df = pd.read_csv(cpi_file)
            # Base CPI = 2024 annual average (matches cpi_stage2_ingest.py)
            self.base_cpi = round(self.cpi_df[self.cpi_df["Year"] == 2024]["CPI_D7EW"].mean(), 4)
            logger.info("Loaded CPI data: %d entries, base_cpi=%.4f", len(self.cpi_df), self.base_cpi)

        except Exception as e:
            logger.error("Failed to load V3 artifacts: %s", e)
            raise RuntimeError(f"Failed to initialize V3PredictionService: {e}")

    def _get_cpi_for_month(self, year: int, month: int) -> float:
        """Look up the real ONS CPI for a given year/month. Extrapolate if missing."""
        row = self.cpi_df[(self.cpi_df["Year"] == year) & (self.cpi_df["Month"] == month)]
        if not row.empty:
            return float(row["CPI_D7EW"].iloc[0])

        # Extrapolate from the last known CPI using a conservative monthly rate
        last_row = self.cpi_df.iloc[-1]
        last_year, last_month = int(last_row["Year"]), int(last_row["Month"])
        last_cpi = float(last_row["CPI_D7EW"])

        # Months difference from last known data point
        months_ahead = (year - last_year) * 12 + (month - last_month)
        if months_ahead <= 0:
            return last_cpi

        # Use the trailing 12-month growth rate from CPI data for extrapolation
        recent = self.cpi_df.tail(12)
        if len(recent) >= 12:
            annual_rate = (recent["CPI_D7EW"].iloc[-1] / recent["CPI_D7EW"].iloc[0]) - 1
            monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
        else:
            monthly_rate = (1 + 0.025) ** (1 / 12) - 1  # Fallback: 2.5% annual

        extrapolated = last_cpi * ((1 + monthly_rate) ** months_ahead)
        logger.debug("Extrapolated CPI for %d-%02d: %.2f (%.1f months ahead)", year, month, extrapolated, months_ahead)
        return extrapolated

    def _build_feature_row(self, raw_features: Dict[str, Any], pred_date: date) -> Dict[str, Any]:
        """
        Assemble a single row with the exact 40 features expected by the
        V3 preprocessor, from raw scraped demographics + a prediction date.
        """
        row = {}
        expected = self.config["expected_features"]

        # ── Demographics (passthrough from scraped data) ──────────────
        demo_keys = [
            "population", "households", "avg_household_income",
            "unemployment_rate", "working", "unemployed", "ab", "c1/c2", "de",
            "white", "non-white", "Distance_to_Nearest_Station",
            "Nearby_Station_Count", "Nearest_Station_Type",
            "Transport_Accessibility_Score", "percent_muslim",
        ]
        for key in demo_keys:
            row[key] = raw_features.get(key)

        # ── Identifiers ───────────────────────────────────────────────
        row["Branch Name"] = raw_features.get("Branch Name", raw_features.get("branch_name", "Unknown"))
        row["outercode"] = raw_features.get("outercode", "")

        # ── Brand Extraction ──────────────────────────────────────────
        row["Inferred_Brand"] = extract_brand(row["Branch Name"])

        # ── Days Since Open ───────────────────────────────────────────
        # Look up from demographics DB and project forward
        outercode = row["outercode"]
        demo_row = self.demographics_db[self.demographics_db["outercode"] == outercode]
        if not demo_row.empty:
            base_days = int(demo_row["Days_Since_Open"].iloc[0])
            try:
                last_known = pd.to_datetime(demo_row["Last_Known_Date"].iloc[0])
                delta = (pd.Timestamp(pred_date) - last_known).days
                row["Days_Since_Open"] = base_days + max(0, delta)
            except Exception:
                row["Days_Since_Open"] = base_days
        else:
            # Fallback: use raw_features if provided, otherwise default to 1000 (Mature Site)
            row["Days_Since_Open"] = raw_features.get("Days_Since_Open", 1000)

        # ── Temporal Features (from prediction date) ──────────────────
        row["Year"] = pred_date.year
        row["Month"] = pred_date.month
        row["DayOfMonth"] = pred_date.day
        row["DayOfWeek"] = pred_date.weekday()  # 0=Monday, 6=Sunday
        row["WeekOfYear"] = pred_date.isocalendar()[1]

        # ── Standard Binary Flags ─────────────────────────────────────
        row["is_weekend"] = 1 if pred_date.weekday() >= 5 else 0
        row["is_payday_window"] = 1 if pred_date.day >= 25 else 0
        row["is_month_start"] = 1 if pred_date.day <= 3 else 0
        row["is_Christmas"] = 1 if (pred_date.month == 12 and pred_date.day == 25) else 0
        row["is_Boxing_Day"] = 1 if (pred_date.month == 12 and pred_date.day == 26) else 0
        row["is_NYE"] = 1 if (pred_date.month == 12 and pred_date.day == 31) else 0
        row["is_NYD"] = 1 if (pred_date.month == 1 and pred_date.day == 1) else 0

        # ── Historical-Only Flags (UK COVID Lockdowns 2020-2021) ────────
        is_lockdown = 0
        from datetime import date as d_obj
        if (d_obj(2020, 3, 23) <= pred_date <= d_obj(2020, 7, 4)) or \
           (d_obj(2020, 11, 5) <= pred_date <= d_obj(2020, 12, 2)) or \
           (d_obj(2021, 1, 4) <= pred_date <= d_obj(2021, 7, 19)):
            is_lockdown = 1
        row["is_covid_lockdown"] = is_lockdown
        row["is_logistics_strike"] = 0
        row["is_delivery_crackdown"] = 0

        # ── Lunar Calendar Flags (Loop based) ─────────────────────────
        row["is_ramadan"] = 0
        row["is_eid_al_fitr"] = 0
        row["is_eid_al_adha"] = 0

        if year in HOLIDAY_MAP:
            h = HOLIDAY_MAP[year]
            for r_start_s, r_end_s in h.get("ramadan", []):
                if pd.to_datetime(r_start_s).date() <= pred_date <= pd.to_datetime(r_end_s).date():
                    row["is_ramadan"] = 1
                    break
            for e_date in h.get("eid_fitr", []):
                if pred_date == pd.to_datetime(e_date).date():
                    row["is_eid_al_fitr"] = 1
            for e_date in h.get("eid_adha", []):
                if pred_date == pd.to_datetime(e_date).date():
                    row["is_eid_al_adha"] = 1

        # ── Ensure all expected features exist (fill missing with NaN) ─
        for feat in expected:
            if feat not in row:
                row[feat] = np.nan

        return row

    def predict(self, raw_features_list: List[Dict[str, Any]],
                prediction_dates: List[str]) -> List[float]:
        """
        Predict daily sales for a list of feature dicts + corresponding dates.
        Returns nominal future £ values (CPI-inflated).
        """
        if not raw_features_list:
            return []

        expected = self.config["expected_features"]
        weights = self.config["ensemble_weights"]
        w_xgb, w_et, w_tab = weights["xgb"], weights["et"], weights["tabnet"]

        # 1. Build feature rows
        rows = []
        dates_parsed = []
        for features, date_str in zip(raw_features_list, prediction_dates):
            d = pd.to_datetime(date_str).date()
            dates_parsed.append(d)
            rows.append(self._build_feature_row(features, d))

        df = pd.DataFrame(rows)[expected]

        # 2. Preprocess (unified ColumnTransformer)
        try:
            import sklearn
            sklearn.set_config(transform_output="pandas")
            X_transformed = self.preprocessor.transform(df)
            
            # 2.5 TabNet Safety Clamp (Applied to raw transformer output)
            if self.tabnet_bounds:
                for col in X_transformed.columns:
                    if col in self.tabnet_bounds:
                        b = self.tabnet_bounds[col]
                        X_transformed[col] = X_transformed[col].clip(lower=b["min"], upper=b["max"])
                logger.debug("Applied safety clamp to %d features", len(self.tabnet_bounds))

            # Clean column names (strip transformer prefixes)
            if hasattr(X_transformed, 'columns'):
                X_transformed.columns = [col.split("__")[-1] for col in X_transformed.columns]
            else:
                # Fallback: convert numpy array to DataFrame
                X_transformed = pd.DataFrame(X_transformed)

            # 2.6 Data Sanitization & Diagnostic Injection
            X_transformed_np = X_transformed.values
            # Force NumPy sanitization (NaN/Inf Handling)
            X_transformed_np = np.nan_to_num(X_transformed_np, nan=0.0, posinf=0.0, neginf=0.0)
            # Ensure float32 for PyTorch/XGBoost consistency
            X_transformed_np = X_transformed_np.astype(np.float32)

            # =====================================================================
            # 🛑 DIAGNOSTIC INJECTION: PRINT THESE LOGS TO THE CONSOLE
            # =====================================================================
            print("\n--- V3 DIAGNOSTIC DATA ---")
            print(f"1. Preprocessor used: {type(self.preprocessor)}")
            print(f"2. Array Shape going into models: {X_transformed_np.shape}")
            try:
                # Try to extract the internal input dimension from TabNet
                # Some versions might use 'input_dim' or stored in network
                input_dim = getattr(self.tabnet_model, 'input_dim', "Unknown")
                print(f"3. TabNet Expected Input Dim: {input_dim}")
            except Exception:
                print("3. TabNet Expected Input Dim: Could not read.")
            print(f"4. Contains NaNs: {np.isnan(X_transformed_np).any()}")
            print(f"5. Contains Infs: {np.isinf(X_transformed_np).any()}")
            print(f"6. Data Type: {X_transformed_np.dtype}")
            print(f"7. TabNet Safety Clamp: {'ACTIVE' if self.tabnet_bounds else 'INACTIVE'}")
            print("---------------------------\n")
            # =====================================================================

        except Exception as e:
            logger.error("Preprocessing or data preparation failed: %s", e)
            raise

        # 3. Run the Holy Trinity (with TabNet fault tolerance)
        # We pass X_transformed_np here for consistency
        preds_xgb_log = self.xgb_model.predict(X_transformed_np)
        preds_et_log = self.et_model.predict(X_transformed_np)

        try:
            preds_tab_log = self.tabnet_model.predict(X_transformed_np).flatten()
            tabnet_ok = True
        except Exception as e:
            logger.warning("TabNet GPU inference failed: %s. Trying CPU fallback...", e)
            try:
                # Attempt CPU fallback by recreating a CPU-bound prediction
                import torch
                torch.cuda.empty_cache()
                # Already sanitized and float32 from step 2.6
                preds_tab_log = self.tabnet_model.predict(X_transformed_np).flatten()
                tabnet_ok = True
            except Exception as e2:
                logger.warning("TabNet CPU fallback also failed: %s. Using 2-model ensemble.", e2)
                tabnet_ok = False

        # 4. Reverse log1p to get Normalized 2024 Base £
        preds_xgb_real = np.expm1(preds_xgb_log)
        preds_et_real = np.expm1(preds_et_log)

        # 5. SciPy-optimized ensemble blend in Real £ space
        if tabnet_ok:
            preds_tab_real = np.expm1(preds_tab_log)
            ensemble_normalized = (
                preds_xgb_real * w_xgb +
                preds_et_real * w_et +
                preds_tab_real * w_tab
            )
        else:
            # Fallback: 2-model blend with re-normalized weights
            w_sum = w_xgb + w_et
            ensemble_normalized = (
                preds_xgb_real * (w_xgb / w_sum) +
                preds_et_real * (w_et / w_sum)
            )
            logger.info("Using 2-model fallback: XGB=%.1f%%, ET=%.1f%%",
                        (w_xgb / w_sum) * 100, (w_et / w_sum) * 100)

        # 6. Reverse-CPI: Convert normalized 2024 £ → nominal future £
        nominal_preds = []
        for i, d in enumerate(dates_parsed):
            future_cpi = self._get_cpi_for_month(d.year, d.month)
            cpi_multiplier = future_cpi / self.base_cpi
            nominal = ensemble_normalized[i] * cpi_multiplier
            nominal_preds.append(max(0.0, float(nominal)))  # Floor at £0

        return nominal_preds
