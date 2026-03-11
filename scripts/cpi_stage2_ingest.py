"""
CPI STAGE 2 — INGEST
====================
1. Load cached CPI data
2. Compute base CPI (2024 annual average)
3. Join CPI onto master CSV by Year-Month
4. Create Total_Sale_Normalized = Total_Sale × (base_CPI / month_CPI)
5. Never touch NaN Total Sale rows (leave as NaN)
6. Save master CSV
"""
import pandas as pd
import numpy as np
from datetime import datetime

MASTER_CSV = r"d:\Location-Analyzer-Prediction-\data\processed\v3_master_combined.csv"
CPI_CACHE  = r"d:\Location-Analyzer-Prediction-\data\processed\cpi_d7ew_restaurants.csv"
BACKUP_CSV = r"d:\Location-Analyzer-Prediction-\data\processed\v3_master_combined_BACKUP_before_cpi.csv"

SEP = "=" * 65

print(SEP)
print("  CPI NORMALIZATION — STAGE 2: INGEST")
print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

# ── Load ──────────────────────────────────────────────────────────
print("\n[1/5] Loading data...")
df     = pd.read_csv(MASTER_CSV, low_memory=False)
cpi_df = pd.read_csv(CPI_CACHE)
df['Date']       = pd.to_datetime(df['Date'], errors='coerce')
df['Total Sale'] = pd.to_numeric(df['Total Sale'], errors='coerce')
print(f"  Master CSV:  {len(df):,} rows")
print(f"  CPI records: {len(cpi_df):,} monthly entries")

# ── Safety: column must not already exist ─────────────────────────
if 'Total_Sale_Normalized' in df.columns:
    print("  NOTE: Total_Sale_Normalized already exists — will OVERWRITE")

# ── Backup ────────────────────────────────────────────────────────
df.to_csv(BACKUP_CSV, index=False)
print(f"  Backup: {BACKUP_CSV}")

# ── Base CPI ──────────────────────────────────────────────────────
print("\n[2/5] Computing base CPI (2024 average)...")
base_cpi = round(cpi_df[cpi_df['Year'] == 2024]['CPI_D7EW'].mean(), 4)
print(f"  Base CPI: {base_cpi}")

# ── Join ──────────────────────────────────────────────────────────
print("\n[3/5] Joining CPI to master CSV by Year-Month...")
df['_YearMonth'] = df['Date'].dt.strftime('%Y-%m')
cpi_lookup = cpi_df.set_index('YearMonth')['CPI_D7EW'].to_dict()
df['_CPI'] = df['_YearMonth'].map(cpi_lookup)

matched   = df['_CPI'].notna().sum()
unmatched = df['_CPI'].isna().sum()
print(f"  Rows matched with CPI:   {matched:,}")
print(f"  Rows WITHOUT CPI match:  {unmatched:,}  (NaN date rows expected)")

# ── Normalize ─────────────────────────────────────────────────────
print("\n[4/5] Computing Total_Sale_Normalized...")
# Only normalize rows with BOTH a valid Total Sale AND a valid CPI
has_sale = df['Total Sale'].notna()
has_cpi  = df['_CPI'].notna()
can_norm = has_sale & has_cpi

df['Total_Sale_Normalized'] = np.nan  # default NaN for all

df.loc[can_norm, 'Total_Sale_Normalized'] = (
    df.loc[can_norm, 'Total Sale'] *
    (base_cpi / df.loc[can_norm, '_CPI'])
).round(2)

normalized_count = df['Total_Sale_Normalized'].notna().sum()
sale_rows        = df['Total Sale'].notna().sum()
print(f"  Total Sale rows:             {sale_rows:,}")
print(f"  Normalized rows created:     {normalized_count:,}")
print(f"  Rows still NaN (no sale):    {sale_rows - normalized_count:,}")

# Sanity: 2024 rows should be ~1:1 ratio
q4_2024 = df[(df['_YearMonth'] >= '2024-01') & (df['_YearMonth'] <= '2024-12') & has_sale]
ratio = (q4_2024['Total_Sale_Normalized'] / q4_2024['Total Sale']).mean()
print(f"\n  Sanity check: 2024 Normalized/Raw ratio = {ratio:.4f}  (should be ~1.000)")

# ── Cleanup temp columns ──────────────────────────────────────────
df = df.drop(columns=['_YearMonth', '_CPI'])

# ── Save ──────────────────────────────────────────────────────────
print("\n[5/5] Saving master CSV...")
df.to_csv(MASTER_CSV, index=False)

print(f"\n{SEP}")
print(f"  STAGE 2 SUMMARY")
print(f"  Rows processed:          {len(df):,}")
print(f"  Total_Sale_Normalized:   {normalized_count:,} values created")
print(f"  Base CPI used:           {base_cpi} (2024 annual avg)")
print(f"  CPI source:              ONS D7EW Restaurants & Cafes")
print(f"\n  DONE — proceed to Stage 3 verification")
print(f"{SEP}\n")
