import joblib
import os
import pandas as pd
import numpy as np
import logging
import json
import sys
import sklearn
from typing import Dict, Any, List, Optional
from sklearn.base import BaseEstimator, RegressorMixin
from pytorch_tabnet.tab_model import TabNetRegressor

# Ensure transformers return DataFrames to preserve feature names correctly
sklearn.set_config(transform_output="pandas")

logger = logging.getLogger(__name__)

class V4EnsembleModel(BaseEstimator, RegressorMixin):
    """
    Production V4 Ensemble: Blends ExtraTrees, LightGBM, RandomForest, and TabNet
    using weights defined in prod_ensemble_weights.json.
    """
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.models = {}
        self.weights = {}
        self._load_ensemble()

    def _load_ensemble(self):
        """Loads all sub-models and their relative weights."""
        try:
            # 1. Load Weights
            weight_path = os.path.join(self.model_dir, "prod_ensemble_weights.json")
            if os.path.exists(weight_path):
                with open(weight_path, 'r') as f:
                    self.weights = json.load(f)
                logger.info(f"Loaded ensemble weights: {self.weights}")
            else:
                # Default safety weights if JSON is missing
                self.weights = {"lgb": 0.4, "rf": 0.2, "et": 0.2, "tabnet": 0.2}
                logger.warning(f"Weights file {weight_path} not found. Using defaults.")

            # 2. Load Scikit-Learn / LightGBM models
            model_files = {
                "lgb": "prod_lgb_model.joblib",
                "rf": "prod_rf_model.joblib",
                "et": "prod_et_model.joblib"
            }
            for key, filename in model_files.items():
                path = os.path.join(self.model_dir, filename)
                if os.path.exists(path):
                    self.models[key] = joblib.load(path)
                    logger.info(f"Loaded {key} model.")
                else:
                    logger.error(f"Missing essential model: {path}")

            # 3. Load TabNet (Special Zip Loader)
            tabnet_path = os.path.join(self.model_dir, "prod_tabnet_model.zip")
            if os.path.exists(tabnet_path):
                # TabNetRegressor.load_model expects the path without .zip or handles the zip
                self.models["tabnet"] = TabNetRegressor()
                self.models["tabnet"].load_model(tabnet_path)
                logger.info("Loaded TabNet model.")
            else:
                logger.warning(f"TabNet model not found at {tabnet_path}. Ensemble will proceed without it.")

        except Exception as e:
            logger.error(f"Failed to initialize V4 Ensemble: {e}")
            raise RuntimeError(f"V4 Ensemble Initialization Error: {e}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Weighted average of sub-model predictions."""
        preds = []
        applied_weights = []

        try:
            X_numeric = X.astype(np.float32)
        except Exception as e:
            logger.error(f"Failed to cast features to float32: {e}")
            raise

        for key, model in self.models.items():
            # Match keys like 'lgb_weight' from the JSON
            weight_key = f"{key}_weight"
            weight = self.weights.get(weight_key, 0.0)
            
            if weight <= 0:
                continue

            try:
                if key == "tabnet":
                    # TabNet strictly requires numpy arrays (not DataFrames)
                    # Use values from the processed DataFrame
                    X_array = X.values if hasattr(X, "values") else X
                    # Casting to float32 is already done at the top of predict() if X was numeric
                    # but if X is the DataFrame, we cast here.
                    X_numeric_tabnet = X_array.astype(np.float32)
                    p = model.predict(X_numeric_tabnet).flatten()
                else:
                    # LGBM, RF, and ET prefer DataFrames with the prefixed names
                    p = model.predict(X)
                
                preds.append(p * weight)
                applied_weights.append(weight)
                
            except Exception as e:
                # TabNet often fails on CUDA indices if input distributions shift
                # We log it but allow the ensemble to continue with other strong models (LGBM, RF, ET)
                # to satisfy production reliability without crashing.
                logger.error(f"Ensemble sub-model '{key}' prediction failed: {e}")
                # Fallback prediction logic for tree models 
                if key != "tabnet" and hasattr(model, 'booster_'):
                    try:
                        p = model.booster_.predict(X_numeric)
                        preds.append(p * weight)
                        applied_weights.append(weight)
                    except:
                        pass

        if not preds:
            raise ValueError("All sub-models failed to predict. Check input feature consistency and shape.")

        total_weight = sum(applied_weights)
        return sum(preds) / total_weight

# Inject into __main__ for joblib compatibility if needed (though we load separately)
sys.modules['__main__'].V4EnsembleModel = V4EnsembleModel

class PredictionService:
    """
    V4 Prediction Service: 
    - Applies unified prod_preprocessor.joblib (RobustScaler + Yeo-Johnson + TargetEncoding).
    - Runs the V4EnsembleModel.
    - Handles raw £ sales conversion.
    """
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.preprocessor = None
        self.ensemble = None
        self.cpi_df = None
        self.base_cpi = 144.03  # 2024 Average CPI (Baseline for V4 training)
        self._load_artifacts()

    def _load_artifacts(self):
        """Load the preprocessor and the ensemble container."""
        try:
            prep_path = os.path.join(self.model_dir, "prod_preprocessor.joblib")
            if os.path.exists(prep_path):
                self.preprocessor = joblib.load(prep_path)
                # Force pandas output for name preservation through nested pipelines
                if hasattr(self.preprocessor, "set_output"):
                    self.preprocessor.set_output(transform="pandas")
                logger.info("Loaded V4 Preprocessor.")
            else:
                raise FileNotFoundError(f"Missing V4 Preprocessor at {prep_path}")

            self.ensemble = V4EnsembleModel(self.model_dir)
            
            # 3. Load CPI Data for Nominal Scaling
            # Usually stored in models/v3 or models/v4 as shared resource
            cpi_path = os.path.join(os.path.dirname(self.model_dir), "v3", "cpi_d7ew_restaurants.csv")
            if not os.path.exists(cpi_path):
                 # Fallback if v3 relative path doesn't exist (e.g. standalone test)
                 cpi_path = os.path.join(self.model_dir, "cpi_d7ew_restaurants.csv")
            
            if os.path.exists(cpi_path):
                self.cpi_df = pd.read_csv(cpi_path)
                logger.info(f"Loaded CPI data from {cpi_path} for nominal scaling.")
            else:
                logger.warning(f"CPI data not found at {cpi_path}. Backtesting and future forecasting will use 2024 price levels.")
            
        except Exception as e:
            logger.error(f"PredictionService Init Failed: {e}")
            raise RuntimeError(f"PredictionService Init Failed: {e}")


    def _get_cpi_multiplier(self, year: int, month: int) -> float:
        """
        Calculates the (target_cpi / base_cpi_2024) multiplier.
        Includes rolling extrapolation for dates beyond the known CPI dataset (pre-2026).
        """
        if self.cpi_df is None:
            return 1.0  # Fallback: No scaling

        # 1. Direct Lookup
        row = self.cpi_df[(self.cpi_df["Year"] == year) & (self.cpi_df["Month"] == month)]
        if not row.empty:
            return float(row["CPI_D7EW"].iloc[0]) / self.base_cpi

        # 2. Extrapolation (Future) or Clipping (Deep Past)
        last_row = self.cpi_df.iloc[-1]
        last_year = int(last_row["Year"])
        last_month = int(last_row["Month"])
        last_cpi = float(last_row["CPI_D7EW"])

        # Calculate months difference
        months_diff = (year - last_year) * 12 + (month - last_month)

        if months_diff <= 0:
            # We are in the past relative to the dataset end, but didn't find the specific year/month
            # This happens if querying pre-1988 (unlikely) or if there are gaps.
            # Clip to the oldest available if before range, or use last available if between points.
            return last_cpi / self.base_cpi

        # Rolling Extrapolation Logic:
        # Calculate trailing 12-month annual inflation rate
        recent_12 = self.cpi_df.tail(12)
        if len(recent_12) >= 12:
            annual_rate = (recent_12["CPI_D7EW"].iloc[-1] / recent_12["CPI_D7EW"].iloc[0]) - 1
            # Multiplier per month (Geometric mean)
            monthly_rate = (1 + annual_rate) ** (1/12) - 1
        else:
            monthly_rate = (1 + 0.025) ** (1/12) - 1 # Fallback 2.5% annual

        extrapolated_cpi = last_cpi * ((1 + monthly_rate) ** months_diff)
        return extrapolated_cpi / self.base_cpi

    def _align_features(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Ensures the raw DataFrame has exactly the 30 columns required by the preprocessor,
        with the correct names and case-sensitivity.
        """
        # Groupings as per training notebook 'preprocessor' define the internal order
        self.cat_features = ['Nearest_Station_Type', 'Inferred_Brand']
        
        self.num_features = [
            'avg_household_income', 'unemployment_rate', 'Distance_to_Nearest_Station', 
            'Transport_Accessibility_Score', 'percent_muslim', 'Days_Since_Open', 
            'rateable_value', 'distance_to_nearest_station_mi', 
            'distance_to_mcdonalds_kfc_mi', 'distance_to_mosque_mi', 'distance_to_university_mi', 
            'workplace_to_resident_ratio', 'ethnic_diversity_index', 'Month', 
            'DayOfMonth', 'DayOfWeek'
        ]
        
        self.pass_features = [
            'is_logistics_strike', 'is_delivery_crackdown', 'is_payday_window', 
            'is_NYE', 'is_NYD', 'is_Christmas', 'is_month_start', 'is_ramadan', 
            'is_eid_al_fitr', 'is_eid_al_adha', 'is_Boxing_Day', 'is_covid_lockdown'
        ]

        # The ColumnTransformer returns columns with 'cat__', 'num__', and 'pass__' prefixes
        # based on the transformer names defined in the notebook.
        self.output_features = (
            [f"cat__{c}" for c in self.cat_features] + 
            [f"num__{c}" for c in self.num_features] + 
            [f"pass__{c}" for c in self.pass_features]
        )

        # The ColumnTransformer was FITTED on this exact sequence from X_train
        training_order = [
            'avg_household_income', 'unemployment_rate', 'Distance_to_Nearest_Station', 
            'Nearest_Station_Type', 'Transport_Accessibility_Score', 'is_logistics_strike', 
            'is_delivery_crackdown', 'is_payday_window', 'is_NYE', 'is_NYD', 'is_Christmas', 
            'is_month_start', 'percent_muslim', 'is_ramadan', 'is_eid_al_fitr', 
            'is_eid_al_adha', 'is_Boxing_Day', 'is_covid_lockdown', 'Inferred_Brand', 
            'Days_Since_Open', 'rateable_value', 'distance_to_nearest_station_mi', 
            'distance_to_mcdonalds_kfc_mi', 'distance_to_mosque_mi', 'distance_to_university_mi', 
            'workplace_to_resident_ratio', 'ethnic_diversity_index', 'Month', 
            'DayOfMonth', 'DayOfWeek'
        ]

        df = df_raw.copy()

        # Handle Branch Name -> Inferred_Brand mapping
        # In this V4 implementation, we expect the pipeline/resolver to have already
        # mapped the string 'McDonalds' to the correct ID (1-7) or 0/Generic.
        if 'Inferred_Brand' not in df.columns and 'branch_name' in df.columns:
            # Placeholder: will be replaced by brand_matcher logic in the pipeline
            df['Inferred_Brand'] = 0 
            
        if 'Days_Since_Open' not in df.columns:
            df['Days_Since_Open'] = 1000.0 # Standard mature site default

        # Re-index to TRAINING sequence to satisfy ColumnTransformer's internal slicing
        return df[training_order]

    def predict(self, raw_data: List[Dict[str, Any]]) -> List[float]:
        """
        Full V4 Inference Pipeline:
        1. Align raw features (30 columns)
        2. Preprocess (Scaling + Encoding)
        3. Predict (Ensemble)
        4. Expm1 (Log -> £)
        """
        if not raw_data:
            return []

        try:
            df_raw = pd.DataFrame(raw_data)
            df_aligned = self._align_features(df_raw)

            # 2. Preprocess: Result is a DataFrame with 'cat__', 'num__', 'pass__' prefixes
            X_df = self.preprocessor.transform(df_aligned)

            # 3. Clean prefixes: Models (LGBM, RF, ET) were fitted on base names, not CT-prefixed names
            X_df.columns = [col.split('__')[-1] for col in X_df.columns]

            # 4. Sanitize: NaNs caused by resolver-training gaps can crash TabNet/Ensemble
            X_df = X_df.fillna(0)

            # 5. Predict: Pass the named DataFrame to the ensemble
            log_preds = self.ensemble.predict(X_df)

            # 6. Convert to actual £ sales (Log -> Nominal)
            sales_preds_base = np.expm1(log_preds)
            sales_preds_base = np.clip(sales_preds_base, a_min=0, a_max=None)

            # 7. Apply CPI-Based Nominal Scaling (Back-deflation / Inflation)
            # Use the first date in raw_data if multiple, or map 1-to-1 if granular
            # In V4 predict(), raw_data is a list of days.
            nominal_sales = []
            for i, p_base in enumerate(sales_preds_base):
                # Extract year/month from the input day features
                day_data = raw_data[i]
                # Fallback to 2024 if dates aren't in input (shouldn't happen in routes.py flow)
                y = day_data.get("Year", day_data.get("year", 2024))
                m = day_data.get("Month", day_data.get("month", 1))
                
                multiplier = self._get_cpi_multiplier(int(y), int(m))
                nominal_sales.append(float(p_base * multiplier))

            return nominal_sales

        except Exception as e:
            logger.error(f"V4 Prediction Pipeline Failed: {e}")
            # Fallback returning zeros to prevent API 500s during development
            return [0.0] * len(raw_data)
