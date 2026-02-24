# Location Analyzer v2 — Machine Learning Strategy

## Overview
The V2 inference pipeline utilizes a fully custom **XGBoost Regressor**, augmented by strict Scikit-Learn pre-processing objects. The objective is to predict Weekly Sales Revenue (£) based purely on surrounding geographic attributes without requiring historical internal sales inputs.

---

## 1. Feature Engineering (The 10-Step Pipeline)
Unlike simple models, this pipeline applies mathematically intensive scaling to handle the high variance of UK postcodes (e.g., Central London vs Rural Wales). This logic is perfectly mirrored between `notebooks/Machine_Learning_Pipeline.ipynb` (Training) and `src/ml/predict.py` (Inference):

1. **Population Capping**: Caps population values to `30,000` to prevent out-of-distribution (OOD) extrapolation for highly dense postcodes.
2. **Log1p Transformations**: Uses `np.log1p` to linearize exponentially right-skewed data like `households` and `Distance_to_Nearest_Station`.
3. **Square Root Scaling**: Applied to specific counter integers like `Nearby_Station_Count` to dampen variance.
4. **QuantileTransform**: Uniform mapping for minority demographics (`non-white`).
5. **K-Bins Discretization**: Segments financial metrics (`unemployed`, `ab`, `de` social classes) into unified K-Means derived categorical bands.
6. **Yeo-Johnson PowerTransform**: Applied to specific target vectors (`working`, `c1/c2`) to enforce Gaussian distribution curves.
7. **RobustScaling**: Prevents millionaire outliers from destroying income features (`avg_household_income`).
8. **Suspicious Zeros Mask**: Synthesizes a binary flag for missing historical data vs true geographical zeroes.
9. **Ordinal Encoding**: Maps explicit integers onto the `Transport_Accessibility_Score`.
10. **Time-Series Injection**: Given a single location record, parses the target future `Month` and generates seasonal variables.

---

## 2. Target Variable Optimization
*   Fast food revenue natively sits on a bounded, right-skewed curve (You cannot make less than £0, but high-performers can make £30k+). 
*   Because of this, the ML target was trained in **Log-Space**.
*   **During inference:** the XGBoost model outputs Log-Outputs (e.g., `8.2`).
*   The API automatically performs `np.expm1()` on this value to transform the Log-Space prediction into a human-readable GBP figure (e.g., `£3,640.95`).
*   Finally, `np.clip` bounds the minimum possible output to `0` to prevent absurd mathematical anomalies.

---

## 3. Artifact Management

The finalized system exports not just the tree logic, but the exact transformation weights generated during training. These are loaded safely into FastApi RAM during boot.

*   `xgboost_sales_model_v2.pkl`
*   `quantile_transformer.pkl`
*   `kbins_discretizer.pkl`
*   `power_transformer.pkl`
*   `robust_scaler.pkl`
*   `ordinal_encoder.pkl`
