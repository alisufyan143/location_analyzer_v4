"""
V3 CLI Prediction Pipeline
==========================
Runs the full Location Analyzer V3 pipeline (Scraping + ML Inference)
directly from the console.

Usage: python scripts/run_v3_pipeline.py
"""

import sys
import os
import logging
import pandas as pd
from datetime import datetime, timedelta

# Ensure project src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from location_analyzer.pipeline.inference_pipeline import InferencePipeline
from location_analyzer.ml.predict_v3 import V3PredictionService
from location_analyzer.config import settings

# ── CONFIGURATION ──────────────────────────────────────────────────────────
# Define the prediction date range here.
# Format: YYYY-MM-DD
FROM = "2025-02-01" 
TO = "2026-02-01" 

# Setup basic logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    print("\n" + "="*70)
    print("  V3 ENTERPRISE PREDICTION PIPELINE (CLI)")
    print("="*70)
    
    # 1. Initialize Pipeline & Service
    print(f"\n[1/4] Initializing V3 Service...")
    try:
        pipeline = InferencePipeline()
        service = V3PredictionService(
            model_dir=settings.ml.v3_models_dir,
            cpi_path=settings.ml.cpi_data_path
        )
        print("✅ Ready.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return

    # 2. Get Postcode Input
    print("\n" + "-"*70)
    postcode = input("  ENTER UK POSTCODE (e.g., HA1 1BA): ").strip().upper()
    if not postcode:
        print("❌ Error: Postcode is required.")
        return
    
    branch_name = input("  ENTER BRANCH NAME (Optional): ").strip()
    print("-"*70)

    # 3. Run Inference Pipeline (Scraping)
    print(f"\n[2/4] Running Inference Pipeline (Scraping & Geocoding)...")
    try:
        # Note: InferencePipeline.run() handles the full scraping orchestration
        features = pipeline.run(postcode)
        if branch_name:
            features["Branch Name"] = branch_name
        print(f"✅ Scraping complete. Collected {len(features)} features.")
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        return

    # 4. Generate Date Range & Predict
    print(f"\n[3/4] Generating Forecast from {FROM} to {TO}...")
    try:
        start_date = datetime.strptime(FROM, "%Y-%m-%d")
        end_date = datetime.strptime(TO, "%Y-%m-%d")
        
        if end_date < start_date:
            print("❌ Error: TO date must be after FROM date.")
            return

        # Generate daily dates
        daily_dates = []
        curr = start_date
        while curr <= end_date:
            daily_dates.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)
            
        print(f"   (Processing {len(daily_dates)} target days)")

        # Run Multi-Model Ensemble Prediction
        # Passing shared features for all dates
        pred_features = [features.copy() for _ in daily_dates]
        raw_preds = service.predict(pred_features, prediction_dates=daily_dates)
        print("✅ Prediction complete.")

    except Exception as e:
        print(f"❌ Prediction failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 5. Display Results
    print(f"\n[4/4] SUMMARY RESULTS:")
    print("="*70)
    print(f"  LOCATION:  {postcode}")
    print(f"  BRANCH:    {features.get('Inferred_Brand', 'Independent')} ({features.get('Branch Name', 'Unknown')})")
    print(f"  PERIOD:    {FROM} to {TO}")
    print("-" * 70)
    
    # 5.1 Weekly Aggregation
    df_results = pd.DataFrame({
        'date': pd.to_datetime(daily_dates),
        'sales': raw_preds
    })
    
    # Monday-based week (resample 'W-MON' labels by week start)
    weekly_summary = df_results.resample('W-MON', on='date').sum().reset_index()
    
    print(f"  WEEKLY FORECASTS:")
    print(f"  {'Week Start':<12} | {'Forecast Sales':<20}")
    print("-" * 40)
    for _, row in weekly_summary.iterrows():
        print(f"  {row['date'].strftime('%Y-%m-%d'):<12} | £{row['sales']:>14,.2f}")
    
    # 5.2 Monthly Aggregation
    print("\n" + "-" * 70)
    print(f"  MONTHLY SUMMARY:")
    df_results['Month'] = df_results['date'].dt.strftime('%b %Y')
    df_results['SortKey'] = df_results['date'].dt.strftime('%Y-%m')
    
    monthly_summary = df_results.groupby(['SortKey', 'Month'])['sales'].sum().reset_index()
    
    print(f"  {'MONTH':<12} | {'FORECAST SALES':<20}")
    print("-" * 40)
    for _, row in monthly_summary.iterrows():
        print(f"  {row['Month']:<12} | £{row['sales']:>14,.2f}")
    
    print("-" * 70)
    total_period = df_results['sales'].sum()
    print(f"  {'TOTAL PERIOD':<12} | £{total_period:>14,.2f}")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
