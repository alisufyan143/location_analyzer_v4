# Docker Deployment Guide

Location Analyzer v2 is fully containerized using Docker and Docker Compose, enabling seamless deployments across any Linux, Windows, or macOS environment without managing Python or Node.js versions.

## System Prerequisites
- Docker Engine
- Docker Compose v2+

## Architecture Overview

The system is composed of two primary lightweight containers:

1.  **`location_analyzer_api`**: 
    - Alpine-based Python 3.11 environment.
    - Mounts `./data`, `./models`, and `./logs` locally for persistent DB and Model caching.
    - Exposes Port `8000`.
    - Includes OS-level dependencies required for headless Chromium (Playwright).

2.  **`location_analyzer_ui`**:
    - Multi-stage build process.
    - Stage 1 compiles the Vite+React application using Node.js.
    - Stage 2 serves the static `/dist` bundle using a high-performance **Nginx** web server.
    - Exposes Port `5173`.

## Quick Start (Local Production)

To build and launch the application ecosystem:

```bash
docker-compose up --build -d
```
*   `--build`: Forces a fresh build of the React bundle and Python dependencies.
*   `-d`: Runs the containers in detached (background) mode.

The services will now be accessible at:
- **Dashboard**: `http://localhost:5173`
- **FastAPI Specs**: `http://localhost:8000/docs`

## Storage & Persistence

Data scraping is an expensive process. The `docker-compose.yml` mounts several local directories into the backend container to ensure data is not lost when the container stops:
*   `./location_analyzer.db:/app/location_analyzer.db` (SQLite caching layer)
*   `./logs:/app/logs` (Python `logging` outputs)

## Rebuilding Services
If you modify the React Frontend (e.g. `ResultsPanel.jsx`), you must rebuild the UI container to clear the Nginx cache:
```bash
docker-compose up -d --build frontend
```

If you modify the Machine Learning pipeline or add new Python scraper models to `src/`:
```bash
docker-compose up -d --build backend
```

## Troubleshooting

**Environment Variables**
Ensure `.env` exists in the local root before running compose. The containers automatically ingest `DATABASE_URL` and Python buffering flags from this file.

**Zombie Playwright Browsers**
If the backend scraper crashes mid-execution, headless Chromium instances may persist in the container's RAM. Restarting the backend container purges them:
```bash
docker-compose restart backend
```
