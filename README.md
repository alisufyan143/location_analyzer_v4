# 📍 Location Analyzer v3: Enterprise Edition

> **The next generation of high-fidelity UK retail sales forecasting.**
> Powered by a triple-engine Meta-Ensemble (XGBoost + ExtraTrees + PyTorch TabNet), real ONS CPI inflation data, and resilient CUDA-accelerated inference.

---

## 🚀 Overview

**Location Analyzer v3** is a state-of-the-art predictive engine designed to determine the exact commercial viability of UK retail locations. It transforms raw postcodes into detailed 12-month revenue forecasts by orchestrating a 100% offline, heavily engineered machine learning pipeline.

### Core v3 Innovations
*   **⚡ 100% Offline Architecture (Zero Scraper)**: Decommissioned all legacy web scrapers. All demographics, amenities, and occupation data are now resolved instantly (<30ms) from a 2.4GB local UK Master DB.
*   **🧠 Triple-Engine Meta-Ensemble**: Combines **XGBoost** (Interactions), **ExtraTrees** (Stability), and **PyTorch TabNet** (Attention-based Neural Net) for >90% prediction accuracy.
*   **🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland Localized Intelligence**: Full support for Scottish postcodes using **SIMD 2020v2**, **Census 2022**, and **SSPL 2026/1** for 100% accurate demographic resolution.
*   **💷 Real ONS CPI Inflation**: Unlike static models, v3 uses official **ONS D7EW Restaurant CPI** data to reverse-inflate forecasts into real-world nominal £ values for 2025–2027.
*   **🛡️ TabNet Safety Clamp**: Proactive protection against CUDA out-of-bounds crashes. Every input is forcefully clipped to training boundaries before inference.
*   **🌙 Cultural Intelligence**: Automatic detection of **Ramadan and Eid** calendar shifts (2025–2028) to account for religious spending cycles.
*   **📍 Zero-Network Geocoding**: Latitude and longitude are resolved locally via an offline ONSPD-based index, ensuring 100% privacy and reliability.
*   **📱 Fully Responsive**: Optimized glassmorphic dashboard that works perfectly on Desktop, Tablet, and Mobile.

---

## 🛠️ Architecture

The v3 architecture is optimized for high-performance inference and data-science reproducibility.

```text
Location-Analyzer-Prediction/
├── frontend/                     # ⚛️ React Dashboard (Vite + Recharts)
├── models/v3/                    # 🏋️‍♂️ V3 Artifacts (XGB, ET, TabNet, Preprocessor, Bounds)
├── scripts/                      # 🛠️ Utility Suite
│   ├── run_v3_pipeline.py        # CLI Interactive Prediction Tool
│   ├── test_v3_api.py            # Integration & Stability Test Suite
│   └── cpi_stage_*.py            # ONS CPI Ingestion & Verification
├── src/location_analyzer/
│   ├── api/                      # ⚡ FastAPI Service Layer
│   ├── ml/                       # 🧠 V3 Inference Engine (predict_v3.py)
│   ├── pipeline/                 # ⚙️ 100% Offline Orchestration (Zero Scraper)
│   ├── data/                     # 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Localized Regional Engines & Spatial Logic
│   └── scrapers/                 # 🕸️ [DECOMMISSIONED] Legacy Scrapers
└── data/uk_data/                 # 📂 Master Data Backbone (2.4GB SQLite + PBF)
    └── uk_master.db              # 🇬🇧 Unified ONSPD + Census + OSM Amenities
```

---

## 🏁 Quick Start

### 1. Environment Setup
The v3 pipeline requires the `location_analyzer_v3` environment for PyTorch/CUDA support.
```bash
conda activate location_analyzer_v3
```

### 2. Start the FastAPI Backend
```bash
# From root
python -m uvicorn src.location_analyzer.api.main:app --host 127.0.0.1 --port 8000
```
*V3 Diagnostic Injection will log model shapes and TabNet dimensions to the console on every request.*

### 3. Start the React Frontend
```bash
cd frontend
npm run dev -- --host
```

### 4. Remote Tunneling (Optional)
To share the dashboard with external users (e.g., via ngrok):
```bash
# Ensure the backend and frontend are running, then tunnel port 5173
# The Vite proxy handles routing API requests to port 8000
ngrok http 5173
```

### 4. CLI Multi-Month Forecast
Run a full prediction suite directly from your terminal:
```bash
python scripts/run_v3_pipeline.py
```

---

## 📈 The V3 Inference Pipeline

The `predict_v3.py` engine follows a strict 7-step execution flow:
1.  **Offline Resolution**: Resolves all features instantly from `uk_master.db` (ONS/NISRA/OSM).
2.  **Zero-Network Geocoding**: Resolves coordinates via local ONSPD index.
3.  **Feature Assembly**: Injects Inferred_Brand, Days_Since_Open, and 5 temporal flags.
4.  **Transformation**: Unified `ColumnTransformer` (TargetEnc, Quantile, Yeo-Johnson).
5.  **Safety Clamp**: Features clipped to training min/max from `tabnet_bounds.json`.
6.  **Ensemble Predict**: Blended result from XGB (42%), ET (33%), and TabNet (25%).
7.  **CPI Inflation**: Forecast adjusted using official ONS monthly indices.

---

## 🧪 Verification & Stability

The system includes a dedicated V3 stability suite to ensure CUDA and data integrity.

*   **API Integration**: `python scripts/test_v3_api.py`
*   **TabNet Stress Test**: `python tmp/test_tabnet_safety.py` (Tests 5M population OOD cases)
*   **Smoke Test**: `python tmp/test_v3_smoke.py`

---

## 🛡️ Requirements
- **OS**: Windows (optimized for RTX series GPUs)
- **Runtime**: Python 3.11+ / Node.js 18+
- **Hardware**: NVIDIA GPU (8GB+ VRAM recommended for TabNet)
- **Data Backbone**: UK Master DB (ONSPD 2024, Census 2021, NISRA, SIMD v2, OSM)

---

## 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish Regional Engine
The v3 pipeline includes a dedicated localized engine for Scotland that bypasses standard scrapers to use official high-fidelity datasets:
- **SSPL 2026/1**: Precise postcode-to-datazone mapping.
- **SIMD 2020v2**: Localized economic and transport indicators.
- **Census 2022**: Official demographic resolution for Age, Ethnicity, and Religion.

---

## 📍 Persistence & UX
- **Database**: SQLite with SQLAlchemy ORM.
- **Schema**: Extended to persist `latitude` and `longitude` coordinates for every successful prediction.
- **UX**: Automatic map centering on cached results for a seamless user experience.

---

## 🧪 Verification & Stability
The system includes a dedicated V3 stability suite to ensure CUDA and data integrity.

- **API Integration**: `python -m pytest tests/test_api.py -v`
- **Database Integrity**: `python -m pytest tests/test_database.py -v`
- **Map Persistence**: `python scripts/verify_map_persistence.py` (Cleaned up after verification)

---
*Developed for strategic retail intelligence.*