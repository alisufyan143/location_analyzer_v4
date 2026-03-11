"""
CPI STAGE 1 — AUDIT
===================
1. Fetch live D7EW (ONS Restaurants & Cafes CPI 2015=100)
2. Parse and verify data quality
3. Check coverage against master CSV date range
4. Preview adjustment factors for key periods
5. Report: safe to proceed to Stage 2?
"""
import requests
import pandas as pd
import io
from datetime import datetime

MASTER_CSV = r"d:\Location-Analyzer-Prediction-\data\processed\v3_master_combined.csv"
ONS_URL = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7ew/mm23"
CPI_CACHE = r"d:\Location-Analyzer-Prediction-\data\processed\cpi_d7ew_restaurants.csv"

SEP = "=" * 65

print(SEP)
print("  CPI NORMALIZATION — STAGE 1: AUDIT")
print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

# ── STEP 1: Fetch ONS data ────────────────────────────────────────
print("\n[1/5] Fetching ONS D7EW (Restaurants & Cafes CPI)...")
print(f"  URL: {ONS_URL}")

headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot)"}
resp = requests.get(ONS_URL, headers=headers, timeout=30)
if resp.status_code != 200:
    print(f"  ERROR: HTTP {resp.status_code}")
    exit(1)

# Parse: the CSV starts with metadata rows, monthly rows look like: "2020 JAN","112.7"
lines = resp.text.strip().split('\n')

rows = []
for line in lines:
    line = line.strip().strip('"')
    parts = line.split('","')
    if len(parts) == 2:
        label, val = parts[0].strip('"'), parts[1].strip('"')
        # Only monthly rows: "YYYY MON" format
        parts2 = label.strip().split()
        if len(parts2) == 2 and parts2[0].isdigit() and len(parts2[0]) == 4:
            try:
                year  = int(parts2[0])
                month = datetime.strptime(parts2[1], "%b").month
                cpi   = float(val)
                rows.append({"Year": year, "Month": month, "CPI_D7EW": cpi,
                             "YearMonth": f"{year}-{month:02d}"})
            except ValueError:
                continue

cpi_df = pd.DataFrame(rows).sort_values(["Year","Month"]).reset_index(drop=True)
print(f"  Fetched {len(cpi_df)} monthly records")
print(f"  Range: {cpi_df['YearMonth'].iloc[0]} → {cpi_df['YearMonth'].iloc[-1]}")

# Save to cache
cpi_df.to_csv(CPI_CACHE, index=False)
print(f"  Cached: {CPI_CACHE}")

# ── STEP 2: Data quality checks ───────────────────────────────────
print("\n[2/5] Data quality checks...")
nulls  = cpi_df['CPI_D7EW'].isna().sum()
zeros  = (cpi_df['CPI_D7EW'] == 0).sum()
dups   = cpi_df['YearMonth'].duplicated().sum()
print(f"  Null values:       {nulls}  (expected: 0)")
print(f"  Zero values:       {zeros}  (expected: 0)")
print(f"  Duplicate months:  {dups}   (expected: 0)")
if nulls == 0 and zeros == 0 and dups == 0:
    print("  PASS: Data is clean")
else:
    print("  WARNING: Issues found — review before proceeding")

# ── STEP 3: Coverage vs master CSV ────────────────────────────────
print("\n[3/5] Checking coverage against master CSV...")
df = pd.read_csv(MASTER_CSV, low_memory=False)
df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
df['Total Sale'] = pd.to_numeric(df['Total Sale'], errors='coerce')

master_months = df.dropna(subset=['Date','Total Sale']).copy()
master_months['YearMonth'] = master_months['Date'].dt.strftime('%Y-%m')
unique_months  = set(master_months['YearMonth'].unique())
cpi_months_set = set(cpi_df['YearMonth'].unique())

missing = sorted(unique_months - cpi_months_set)
covered = unique_months & cpi_months_set

print(f"  Unique months in master CSV:  {len(unique_months)}")
print(f"  Months covered by CPI:        {len(covered)}")
print(f"  Months NOT in CPI:            {len(missing)}")
if missing:
    print(f"  Missing months: {missing}")
else:
    print(f"  FULL COVERAGE: all master CSV months have a CPI value")

# ── STEP 4: Base year calculation ─────────────────────────────────
print("\n[4/5] Base year calculation (2024 average)...")
cpi_2024 = cpi_df[cpi_df['Year'] == 2024]['CPI_D7EW']
base_cpi = round(cpi_2024.mean(), 2)
print(f"  2024 monthly values: {cpi_2024.tolist()}")
print(f"  2024 average CPI:    {base_cpi}  (this is our base)")

# ── STEP 5: Preview adjustment factors ────────────────────────────
print("\n[5/5] Adjustment factor preview (2024 avg = 1.000):")
print(f"\n  {'Year-Month':<12} {'CPI':>8} {'Factor':>10} {'£1000 becomes':>16}")
print(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*16}")

preview_months = [
    "2010-12","2011-01","2012-01","2013-01",
    "2020-01","2021-01","2022-01","2022-06",
    "2023-01","2023-06","2024-01","2024-12",
    "2025-01","2025-06"
]
for ym in preview_months:
    row = cpi_df[cpi_df['YearMonth'] == ym]
    if len(row):
        cpi_val = row.iloc[0]['CPI_D7EW']
        factor  = round(base_cpi / cpi_val, 4)
        adj     = round(1000 * factor, 0)
        print(f"  {ym:<12} {cpi_val:>8.1f} {factor:>10.4f} {adj:>14.0f}")

print(f"\n{SEP}")
print(f"  AUDIT SUMMARY")
print(f"  Source:       ONS D7EW — Restaurants & Cafes CPI 2015=100")
print(f"  Records:      {len(cpi_df)} monthly entries")
print(f"  Master dates: all {len(covered)}/{len(unique_months)} months covered")
print(f"  Base CPI:     {base_cpi} (2024 annual average)")
print(f"  Column to add: Total_Sale_Normalized")
if not missing:
    print(f"\n  AUDIT PASSED — safe to proceed to Stage 2")
else:
    print(f"\n  WARNING: {len(missing)} months without CPI — handle before Stage 2")
print(f"{SEP}\n")
