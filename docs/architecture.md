# Location Analyzer v2 — Global Architecture

## System Overview

Location Analyzer v2 is a decoupled, full-stack ML application. It utilizes separate microservices for data extraction, inference generation, and data visualization.

```text
┌────────────────────────────────────────────────────────┐
│                   React + Vite (Frontend Layer)        │
│    Data Vis: Recharts   |   Geospatial: React-Leaflet  │
└───────────────────────┬────────────────────────────────┘
                        │ HTTP JSON (Axios)
               ┌────────▼────────┐
               │ FastAPI API     │
               │ POST /predict   │
               └────────┬────────┘
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
┌──────────────┐                  ┌──────────────┐
│ Playwright   │                  │ XGBoost ML   │
│ Scrapers     │                  │ Inference    │
│ (Extraction) │                  │ (Prediction) │
└──────┬───────┘                  └──────┬───────┘
       │                                 │
       ▼                                 ▼
┌──────────────┐                  ┌──────────────┐
│.co.uk URLs   │                  │.pkl Artifacts│
└──────────────┘                  └──────────────┘
```

## 1. The Frontend (Phase 5.2)
Built entirely in React using the Vite bundler.
*   **Styling**: Pure Vanilla CSS system (`index.css`) supporting Dark Mode and Glassmorphism without heavy UI frameworks.
*   **State Management**: React Hooks (`useState`) tied directly to asynchronous Axios HTTP calls.
*   **Visuals**: `Recharts` renders the 12-month sales projections as interactive Area Graphs. `React-Leaflet` renders the UK maps using custom CartoDB dark tiles.

## 2. The API Layer (Phase 5.1)
Built in Python using FastAPI.
*   **Lifespan Events**: The heavy machine learning models (`XGBoostRegressor`) and Scikit-Learn transformers (`KBinsDiscretizer`, `PowerTransformer`) are loaded exactly once into memory on server bootup via `app.state`.
*   **Concurrency**: Uses `async/await` to handle incoming HTTP requests without blocking the event loop.
*   **Validation**: Uses strict `Pydantic` `BaseModel` schemas to validate Postcodes before attempting database or scraper interactions.

## 3. The Inference Pipeline (Phase 5)
Orchestrates the scrapers.
*   When `POST /predict` is hit, `InferencePipeline` spins up both `DemographicsScraper` and `CrystalRoofScraper` simultaneously.
*   The raw results (such as `population: 20000`, `nearest_station: 'Underground'`) are merged into a single dictionary.
*   This dictionary's keys are explicitly mapped to match the precise column names expected by the trained ML model.

## 4. The ML Engine (Phase 4)
*   **Transformation**: The raw JSON dictionary is cast to a Pandas DataFrame. It undergoes 10 distinct mathematical transformations (Log1p, Scaling, Squaring) to match the training data state.
*   **Time Series**: To generate the 12-month graph, the ML engine artificially injects future months into the `Date` column and runs the prediction 12 separate times in a vectorized batch.
*   **Output**: Log predictions are reversed using `np.expm1` to return absolute GBP (£) values.
