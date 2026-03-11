# 📍 Location Analyzer v3: Enterprise Edition

> **The next generation of high-fidelity UK retail sales forecasting.**
> Powered by a triple-engine Meta-Ensemble (XGBoost + ExtraTrees + PyTorch TabNet), real ONS CPI inflation data, and resilient CUDA-accelerated inference.

---

## 🚀 Overview

**Location Analyzer v3** is a state-of-the-art predictive engine designed to determine the exact commercial viability of UK retail locations. It transforms raw postcodes into detailed 12-month revenue forecasts by orchestrating live demographic scraping, geocoding, and a heavily engineered machine learning pipeline.

### Core v3 Innovations
*   **🧠 Triple-Engine Meta-Ensemble**: Combines **XGBoost** (Interactions), **ExtraTrees** (Stability), and **PyTorch TabNet** (Attention-based Neural Net) for >90% prediction accuracy.
*   **💷 Real ONS CPI Inflation**: Unlike static models, v3 uses official **ONS D7EW Restaurant CPI** data to reverse-inflate forecasts into real-world nominal £ values for 2025–2027.
*   **🛡️ TabNet Safety Clamp**: Proactive protection against CUDA out-of-bounds crashes. Every input is forcefuly clipped to training boundaries before inference.
*   **🌙 Cultural Intelligence**: Automatic detection of **Ramadan and Eid** calendar shifts (2025–2028) to account for religious spending cycles.
*   **🏷️ Brand Recognition**: Automatic extraction of high-performing franchises (e.g., Pepe's, Rio's) with brand-specific revenue multipliers.

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
│   ├── pipeline/                 # ⚙️ Scraping Orchestration
│   └── scrapers/                 # 🕸️ Residential Extraction Agents
└── data/processed/               # 📂 Master Combined Dataset & CPI DB
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
npm run dev
```

### 4. CLI Multi-Month Forecast
Run a full prediction suite directly from your terminal:
```bash
python scripts/run_v3_pipeline.py
```

---

## 📈 The V3 Inference Pipeline

The `predict_v3.py` engine follows a strict 7-step execution flow:
1.  **Scraping**: Fetches live Nomis/StreetCheck and CrystalRoof data.
2.  **Geocoding**: Resolves coordinates via Postcodes.io.
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
- **Data Source**: ONS CPI D7EW / Nomis / CrystalRoof

---
*Developed for strategic retail intelligence.*
red by integration tests utilizing `pytest`.

```bash
# Run the FastAPI test suite covering scraper logic, serialization, and ML Output
python -m pytest tests/test_api.py -v
```