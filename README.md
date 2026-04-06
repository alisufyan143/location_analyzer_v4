# 📍 Location Analyzer v4: Enterprise Edition

> **The next generation of high-fidelity UK commercial real estate & QSR sales forecasting.**  
> Powered by a SciPy-Optimized Meta-Ensemble (TabNet + ExtraTrees + CatBoost), dynamic time-series maturity logic, and 100% live RAM inference.

---

## 🚀 The V4 Innovations

**Location Analyzer v4** is a state-of-the-art predictive engine designed to determine the exact commercial viability, street physics, and revenue trajectory of UK retail locations. It transforms raw postcodes into detailed, month-by-month revenue forecasts.

### 🌟 What's New in V4?
*   **🧠 SciPy Pruned Meta-Ensemble**: The V4 mathematical core was subjected to Monte-Carlo Meta-Ensemble pruning. It officially runs on a high-efficiency blend of **ExtraTrees (47%)**, **PyTorch TabNet (46%)**, and **CatBoost (6%)**. Redundant tree-models (Random Forest, XGBoost) are aggressively memory-pruned at boot.
*   **⏱️ Dynamic Time-Series Maturity**: Upgraded the machine learning from static snapshots to **true rolling maturity**. The API tracks a physical branch's age (`Days_Since_Open`) and dynamically increments it month-over-month across a 2-year forecast, giving you an exact mathematical growth curve. New queries dynamically default to **Stabilized Year-3 (1000 days)**.
*   **⚡ Live RAM Inference (Cache Stripped)**: We ripped out stale SQLite prediction caching. Since our ONNX/Joblib neural networks execute in ~45ms, all multi-year forecasting is generated live, dynamically, directly in system RAM.
*   **📅 Categorical Date Forcing**: Solved the geographical "Sawtooth" bug by forcing temporal dimensions (`Month`, `DayOfWeek`) into pure strings, locking the preprocessor into treating dates as contexts rather than continuous floats.
*   **🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish & UK Regional Engine**: Uses robust regional feature aggregators (`rateable_value`, `ethnic_diversity_index`, `distance_to_station_mi`) parsed directly by a hyper-tuned `CategoryEncoder`.

---

## 🛠️ Architecture Overview

The V4 architecture separates UI state from geometric math processing, optimizing strictly for speed and data-science reproducibility.

```text
Location-Analyzer-Prediction/
├── frontend/                     # ⚛️ React Dashboard (Vite + Recharts)
│   ├── src/App.jsx               # Main SPA (Ngrok/Proxy agnostic URL routing)
│   └── vite.config.js            # Internal Reverse Proxy Router
├── models/production/            # 🏋️‍♂️ V4 Final Assets (CatBoost, TabNet.zip, ExtraTrees, Preprocessor)
├── src/location_analyzer/
│   ├── api/                      # ⚡ FastAPI Service Layer (routes.py)
│   ├── ml/                       # 🧠 V4 Live Inference Engine (predict.py)
│   ├── data/                     # 🗄️ SQLAlchemy ORM (models.py) & Ingestion Logic 
│   ├── pipeline/                 # ⚙️ Real-time feature assembly and geo-scraping
│   └── config.py                 # Configuration Matrix (points to models/production)
└── data/uk_data/                 # 📂 Master Data Backbone
    └── uk_master.db              # 🇬🇧 Unified SQlite (Spatial cache & Base Maturity Anchors)
```

---

## 🏁 Quick Start Guide

### 1. Environment Setup
The V4 pipeline strictly requires the `location_analyzer_v3` conda environment for PyTorch & CUDA hardware acceleration.
```bash
conda activate location_analyzer_v3
```

### 2. Boot the Edge Intelligence (FastAPI Backend)
```bash
# Execute from the root directory
python -m uvicorn src.location_analyzer.api.main:app --host 127.0.0.1 --port 8000 --reload
```
*V4 diagnostic routines will instantly print meta-ensemble pruning stats and TabNet shapes to your terminal.*

### 3. Launch the Vite Dashboard (Frontend)
```bash
# Execute in a discrete terminal
cd frontend
npm run dev -- --host
```

### 4. Remote Tunneling (Global UI Access)
V4 has been perfectly optimized for reverse-proxy tunneling. The React code utilizes relative backend pathways `/predict` to securely hit the Vite router. You can easily broadcast the platform to an external phone or remote laptop via Ngrok:
```bash
# Forward the Vite Network port 
ngrok http 5173
```
*Access the resulting `https://...ngrok-free.dev` link anywhere in the world.*

---

## 📈 The V4 Inference Pipeline Execution Path

Whenever a user executes a prediction trace on the frontend, the `PredictionService` handles it in a rigid, 6-phase runtime:
1.  **R1 (Spatial Cache Lookup)**: Checks SQLite if the Postcode's physical geometry and Demographics have been previously analyzed (Saves API limits).
2.  **R2 (Live Scrape)**: If brand new, dynamically maps distance to Train Stations, Mosques, and Fast Food Competitors using `united_resolver`.
3.  **R3 (Dynamic Base Maturity)**: Queries `BranchMaturity` tables. Identifies if the branch already exists and sets its exact operational age baseline.
4.  **R4 (Feature Assembly & Time Generation)**: Rolls a 12/24-month physical calendar forward, geometrically incrementing `Days_Since_Open` against each new date string.
5.  **R5 (Meta-Ensemble Blend)**: Feeds the feature array through the V4 preprocessor. Applies the exact SciPy float weights (e.g. `TabNet` x `0.46`). Reverses logarithmic boundaries (`np.expm1`).
6.  **R6 (Response Serialization)**: Granularizes results into Daily, Weekly, and Monthly arrays back to React.

---

## 🛡️ Minimum Hardware Requirements
- **OS**: Windows (Native optimized)
- **Runtime**: Python 3.11+ / Node.js 18+
- **Hardware**: NVIDIA GPU (CUDA 11/12+). 8GB+ VRAM heavily recommended for uninterrupted Batched PyTorch inference.
- **Cache**: 3GB+ local storage required for the SQLite / Geometric datasets.

---
*Architected and tuned for strategic QSR retail intelligence scaling.*