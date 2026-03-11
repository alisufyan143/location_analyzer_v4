"""
CPI STAGE 3 — CRITICAL VERIFICATION
=====================================
1. Verify Total_Sale_Normalized column exists and has correct count
2. Verify NaN rows were NOT normalized (stayed NaN)
3. Spot-check: manually recompute for 5 random rows and compare
4. Verify 2024 values are ~equal to raw (adjustment ~1.0)
5. Verify 2021 values are ~26% higher than raw (adjustment ~1.26)
6. Show distribution stats: mean, std, min, max before/after
7. Show per-branch average adjustment applied
"""
import pandas as pd
import numpy as np
from datetime import datetime

MASTER_CSV = r"d:\Location-Analyzer-Prediction-\data\processed\v3_master_combined.csv"
CPI_CACHE  = r"d:\Location-Analyzer-Prediction-\data\processed\cpi_d7ew_restaurants.csv"
BASE_CPI   = 144.03

SEP  = "=" * 65
SEP2 = "-" * 65

print(SEP)
print("  CPI NORMALIZATION — STAGE 3: CRITICAL VERIFICATION")
print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

df     = pd.read_csv(MASTER_CSV, low_memory=False)
cpi_df = pd.read_csv(CPI_CACHE)
df['Date']                   = pd.to_datetime(df['Date'], errors='coerce')
df['Total Sale']             = pd.to_numeric(df['Total Sale'], errors='coerce')
df['Total_Sale_Normalized']  = pd.to_numeric(df['Total_Sale_Normalized'], errors='coerce')
cpi_lookup = cpi_df.set_index('YearMonth')['CPI_D7EW'].to_dict()

print(f"\n  Master CSV rows:           {len(df):,}")
print(f"  Columns: {[c for c in df.columns if 'Sale' in c or 'sale' in c]}")

# ── CHECK 1: Column exists + correct counts ────────────────────────
print(f"\n{SEP2}")
print("[CHECK 1] Column existence and counts")
print(SEP2)
norm_count = df['Total_Sale_Normalized'].notna().sum()
sale_count = df['Total Sale'].notna().sum()
nan_sale   = df['Total Sale'].isna().sum()
nan_norm   = df['Total_Sale_Normalized'].isna().sum()

print(f"  Total Sale rows (not NaN):         {sale_count:,}")
print(f"  Total_Sale_Normalized (not NaN):   {norm_count:,}")
print(f"  Difference:                        {sale_count - norm_count}")
match = "PASS" if sale_count == norm_count else "FAIL — counts differ!"
print(f"  Result: {match}")

# ── CHECK 2: NaN rows stayed NaN ──────────────────────────────────
print(f"\n{SEP2}")
print("[CHECK 2] NaN Total Sale rows must remain NaN in Normalized column")
print(SEP2)
nan_rows = df[df['Total Sale'].isna()]
norm_in_nan = nan_rows['Total_Sale_Normalized'].notna().sum()
print(f"  NaN Total Sale rows:               {len(nan_rows):,}")
print(f"  Of those, Normalized is NOT NaN:   {norm_in_nan}")
result = "PASS" if norm_in_nan == 0 else "FAIL — NaN rows got normalized!"
print(f"  Result: {result}")

# ── CHECK 3: Manual spot-check for 5 random rows ──────────────────
print(f"\n{SEP2}")
print("[CHECK 3] Manual spot-check — recompute 5 random rows")
print(SEP2)
valid = df[df['Total Sale'].notna() & df['Date'].notna()].copy()
sample = valid.sample(5, random_state=42)
print(f"  {'Branch':<35} {'Date':<12} {'Raw':>8} {'CPI':>7} {'Expected':>10} {'Got':>10} {'OK?':>6}")
print(f"  {'-'*35} {'-'*12} {'-'*8} {'-'*7} {'-'*10} {'-'*10} {'-'*6}")
all_ok = True
for _, row in sample.iterrows():
    ym  = pd.Timestamp(row['Date']).strftime('%Y-%m')
    cpi = cpi_lookup.get(ym, None)
    if cpi is None: continue
    expected = round(row['Total Sale'] * (BASE_CPI / cpi), 2)
    got      = round(row['Total_Sale_Normalized'], 2)
    ok       = abs(expected - got) < 0.02
    if not ok: all_ok = False
    print(f"  {str(row['Branch Name'])[:35]:<35} {ym:<12} {row['Total Sale']:>8.2f} "
          f"{cpi:>7.1f} {expected:>10.2f} {got:>10.2f} {'OK' if ok else 'FAIL':>6}")
print(f"  Spot-check result: {'ALL PASS' if all_ok else 'FAILURES FOUND'}")

# ── CHECK 4: 2024 rows — ratio should be ~1.0 ─────────────────────
print(f"\n{SEP2}")
print("[CHECK 4] 2024 rows — Normalized/Raw ratio should be ≈1.000")
print(SEP2)
rows_2024 = df[df['Date'].dt.year == 2024].dropna(subset=['Total Sale','Total_Sale_Normalized'])
ratio_2024 = (rows_2024['Total_Sale_Normalized'] / rows_2024['Total Sale']).mean()
print(f"  2024 rows: {len(rows_2024):,}  |  Mean ratio: {ratio_2024:.4f}  (target: 1.000±0.008)")
result = "PASS" if abs(ratio_2024 - 1.0) < 0.01 else "FAIL"
print(f"  Result: {result}")

# ── CHECK 5: 2021 rows — ratio should be ~1.26 ────────────────────
print(f"\n{SEP2}")
print("[CHECK 5] 2021 rows — Normalized/Raw ratio should be ≈1.26")
print(SEP2)
rows_2021 = df[df['Date'].dt.year == 2021].dropna(subset=['Total Sale','Total_Sale_Normalized'])
ratio_2021 = (rows_2021['Total_Sale_Normalized'] / rows_2021['Total Sale']).mean()
print(f"  2021 rows: {len(rows_2021):,}  |  Mean ratio: {ratio_2021:.4f}  (target: ~1.26)")
result = "PASS" if 1.20 < ratio_2021 < 1.32 else "FAIL"
print(f"  Result: {result}")

# ── CHECK 6: Distribution stats before/after ──────────────────────
print(f"\n{SEP2}")
print("[CHECK 6] Distribution: Raw vs Normalized")
print(SEP2)
valid2 = df.dropna(subset=['Total Sale','Total_Sale_Normalized'])
for col, label in [('Total Sale','Raw'), ('Total_Sale_Normalized','Normalized')]:
    s = valid2[col]
    print(f"  {label:<15}: mean=£{s.mean():>8.0f}  std=£{s.std():>8.0f}  "
          f"min=£{s.min():>7.0f}  max=£{s.max():>8.0f}")
diff_pct = 100 * (valid2['Total_Sale_Normalized'].mean() - valid2['Total Sale'].mean()) / valid2['Total Sale'].mean()
print(f"\n  Normalized mean is {diff_pct:+.1f}% vs raw (inflation uplift on historical data)")

# ── CHECK 7: Per-year avg adjustment ──────────────────────────────
print(f"\n{SEP2}")
print("[CHECK 7] Per-year avg adjustment factor")
print(SEP2)
valid3 = df.dropna(subset=['Total Sale','Total_Sale_Normalized']).copy()
valid3['Year'] = valid3['Date'].dt.year
yearly = valid3.groupby('Year').apply(
    lambda g: (g['Total_Sale_Normalized'] / g['Total Sale']).mean()
).round(4)
print(f"  {'Year':<6} {'Avg Factor':>12} {'Meaning':>25}")
for yr, factor in yearly.items():
    pct = (factor - 1) * 100
    print(f"  {yr:<6} {factor:>12.4f}  {'↑' if pct>0 else '↓'}{abs(pct):.1f}% historical uplift")

print(f"\n{SEP}")
print("  VERIFICATION COMPLETE")
all_checks = [
    sale_count == norm_count,
    norm_in_nan == 0,
    all_ok,
    abs(ratio_2024 - 1.0) < 0.01,
    1.20 < ratio_2021 < 1.32
]
passed = sum(all_checks)
print(f"  Checks passed: {passed}/5")
if passed == 5:
    print("  ALL CHECKS PASSED — CPI normalization is correct")
else:
    print("  SOME CHECKS FAILED — review above")
print(SEP)
