# 📍 Location Analyzer v2

> **Production-grade UK postcode analysis tool powering strategic retail expansion.**
> Features live dual-source demographic scraping, a 4-Engine Median Ensemble Machine Learning pipeline (XGBoost, LightGBM, CatBoost, Random Forest) for Time-Series sales forecasting, and an interactive React dashboard.

---

## 🚀 Overview

**Location Analyzer v2** is a robust Full-Stack AI application designed to evaluate the commercial potential of UK postcodes for new retail branches. By aggregating live data from demographic & transport sources (StreetCheck, CrystalRoof) and piping it through an advanced Machine Learning pipeline, it outputs highly accurate £ Sales Revenue projections.

### Key Capabilities
*   **🕸️ Resilient Live Scraping**: Async Playwright Orchestration scraping `postcodearea.co.uk` and `crystalroof.com` simultaneously upon user request.
*   **🤖 Median Ensemble Forecasting**: Evaluates 12+ demographic features, applies rigorous Scikit-Learn transformations, and generates a 12-month trailing sales forecast by aggregating predictions from XGBoost, LightGBM, CatBoost, and Random Forest engines.
*   **📊 Interactive React Dashboard**: A beautiful Dark-Mode `Vite` + `React` interface featuring `Leaflet` geospatial mapping and `Recharts` data visualization.
*   **⚡ FastAPI Microservice**: High-concurrency python backend serving `pydantic` validated JSON APIs.
*   **📄 Comprehensive PDF Export**: A rich client-side engine (`html2canvas` + `jsPDF`) generates mathematically perfect structural PDF reports containing multi-level demographic tables, localized geography data, and cleanly rendered vectorized forecast charts.
*   **🛡️ Resilient Data Engineering**: Strict 30-day Time-To-Live (TTL) SQLite caching, dual-validation constraints to prevent storing incomplete scrapes, and a 5-attempt exponential backoff mechanism to guarantee location placement logic on Postcodes.io dropouts.

---

## 🛠️ Architecture

The project follows a decoupled monolithic architecture separating ML logic, the API serving layer, and the client application.

```text
location_analyzer_v2/
├── frontend/                     # ⚛️ React + Vite Web Dashboard (Phase 5.2)
│   ├── src/components/           # Recharts, Leaflet Map, Glassmorphism UI
│   └── src/index.css             # Vanilla CSS Dark Theme System
├── src/location_analyzer/
│   ├── api/                      # ⚡ FastAPI Service (Phase 5.1)
│   ├── config.py                 # 🔧 Pydantic BaseSettings Environment Management
│   ├── ml/                       # 🧠 Machine Learning Engine (Phase 4)
│   ├── pipeline/                 # ⚙️ Orchestration & Feature Mapping (Phase 5)
│   └── scrapers/                 # 🕸️ Playwright Extraction Agents (Phase 3)
├── models/                       # 🏋️‍♂️ Serialized .pkl Models & Transformers
└── notebooks/                    # 📓 Data Science EDA & Training
```

---

## 🏁 Quick Start

To launch the full-stack application locally, you must run both the Python Backend and the Node.js Frontend simultaneously.

### 1️⃣ Start the FastAPI Backend
Ensure your `conda` environment is activated and dependencies are installed.

```bash
cd location_analyzer_v2
python -m uvicorn src.location_analyzer.api.main:app --reload
```
The API will initialize, load the heavy Median Ensemble `.pkl` artifacts into memory, and begin listening on `http://127.0.0.1:8000`.

### 2️⃣ Start the React Frontend
Open a **second terminal window**.

```bash
cd location_analyzer_v2/frontend
npm install
npm run dev
```

Visit the local URL (usually `http://localhost:5173`) in your browser to interact with the Dashboard.

---

## 🎨 Dashboard UX & Features

Location Analyzer v2 comes packed with features designed for high-density geographic analysis:
- **Interactive Multi-Granular Forecasting**: Instantly toggle between Daily, Weekly, and Monthly prediction horizons utilizing high-performance SVG Recharts.
- **Smart Result Panel Overlays**: Users can seamlessly minimize the heavy data-grid overlay to interact exclusively with the Leaflet map and spatial pinpoints, maintaining core KPIs on screen.
- **On-Demand Cache Busters**: Bypassing the 30-day SQL limit, the frontend exposes a "Force Live Scrape" API flag to bypass internal checks and command the headless browsers to re-evaluate the target market area.
- **A4 PDF Report Generation**: By rendering an invisible structural layout component loaded with localized district/ward markers, restaurant proximities, and transport scores, the application exports high-fidelity presentation-ready analytics dashboards entirely inside the client’s browser.

---

## 📈 The ML Feature Engineering Pipeline

The inference engine strictly mirrors the training preprocessing rules to prevent data-leakage and shape mismatches:
1.  **Imputation & Capping**: Population outliers bounded.
2.  **Log1p Transforms**: Applied to magnitudes (`population`, `Distance_to_Nearest_Station`).
3.  **KBins Discretizer**: KMeans binning for employment statistics.
4.  **PowerTransformer**: Yeo-Johnson transforms for `C1/C2` social classifications.
5.  **Time Series Synthesis**: A 12-month sequential permutation is generated dynamically and fed into the Median Ensemble for seasonal trend modeling across 4 separate sub-models.

---

## 🛡️ Anti-Bot & Rate Limiting Disclaimer
The live `POST /predict` endpoint invokes the `InferencePipeline` which connects to external residential websites. To prevent IP bans, the scrapers in `src/scrapers/` must be configured with Rotating Proxies inside your `.env` file before executing high-volume bulk predictions.

---

## 🧪 Testing

The API and ML inference layers are fully covered by integration tests utilizing `pytest`.

```bash
# Run the FastAPI test suite covering scraper logic, serialization, and ML Output
python -m pytest tests/test_api.py -v
```