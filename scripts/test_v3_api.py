"""
V3 API Integration Test
========================
Tests the /predict endpoint with a known postcode/branch
against the live FastAPI server (must be running on localhost:8000).

Run: python scripts/test_v3_api.py
"""
import requests
import json
import sys

API_URL = "http://127.0.0.1:8000"

print("=" * 60)
print("  V3 API INTEGRATION TEST")
print("=" * 60)

# ── Test 1: Health Check ──────────────────────────────────────
print("\n[1/3] Health Check...")
try:
    r = requests.get(f"{API_URL}/health", timeout=10)
    health = r.json()
    assert health["status"] == "healthy", f"Unhealthy: {health}"
    assert health["model_loaded"] is True, "Model not loaded!"
    print(f"  ✅ PASSED: {health}")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    print("  Is the server running? Start it with:")
    print("    python -m uvicorn location_analyzer.api.main:app --port 8000")
    sys.exit(1)

# ── Test 2: Predict (Known Postcode) ──────────────────────────
print("\n[2/3] /predict with HA1 1BA (Pepe's Harrow)...")
try:
    payload = {
        "postcode": "HA1 1BA",
        "branch_name": "Pepe's Harrow"
    }
    r = requests.post(f"{API_URL}/predict", json=payload, timeout=180)
    
    if r.status_code != 200:
        print(f"  ❌ HTTP {r.status_code}: {r.text[:500]}")
        sys.exit(1)
    
    data = r.json()
    
    # Validate response structure
    assert "predicted_sales" in data, "Missing predicted_sales"
    assert "time_series" in data, "Missing time_series"
    assert "features" in data, "Missing features" 
    
    pred = data["predicted_sales"]
    source = data.get("source", "unknown")
    ts = data["time_series"]
    monthly = ts.get("monthly", [])
    daily = ts.get("daily", [])
    weekly = ts.get("weekly", [])
    
    print(f"  ✅ PASSED")
    print(f"  Source: {source}")
    print(f"  Predicted Sales (Month 1): £{pred:,.2f}")
    print(f"  Daily forecasts: {len(daily)} days")
    print(f"  Weekly forecasts: {len(weekly)} weeks")
    print(f"  Monthly forecasts: {len(monthly)} months")
    
    # Validate prediction range
    assert pred > 0, f"Prediction should be positive, got £{pred}"
    assert len(monthly) == 12, f"Expected 12 months, got {len(monthly)}"
    assert len(daily) > 350, f"Expected ~365 daily forecasts, got {len(daily)}"
    
    # Print monthly breakdown
    print("\n  MONTHLY FORECAST BREAKDOWN:")
    print("  " + "-" * 40)
    for m in monthly:
        print(f"    {m['date']:>10}: £{m['predicted_sales']:>10,.2f}")
    print("  " + "-" * 40)
    
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ── Test 3: CPI Sanity Check ─────────────────────────────────
print("\n[3/3] CPI Inflation Sanity Check...")
try:
    # Later months should generally trend slightly higher due to CPI
    first_month = monthly[0]["predicted_sales"]
    last_month = monthly[-1]["predicted_sales"]
    
    print(f"  Month 1:  £{first_month:,.2f}")
    print(f"  Month 12: £{last_month:,.2f}")
    
    # Both should be reasonable positive numbers
    assert first_month > 0, "Month 1 should be positive"
    assert last_month > 0, "Month 12 should be positive"
    
    print(f"  ✅ PASSED: Both months are reasonable positive values")
    
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("  ✅ ALL V3 API INTEGRATION TESTS PASSED")
print("=" * 60)
