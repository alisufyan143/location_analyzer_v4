import pandas as pd
import numpy as np
import shutil
import os

MASTER_CSV = r'd:\Location-Analyzer-Prediction-\data\processed\v3_master_combined.csv'
BACKUP_CSV = r'd:\Location-Analyzer-Prediction-\data\processed\v3_master_combined_pre_brand_maturity.csv'

def extract_brand(name):
    name = str(name).lower()
    if "pepe" in name: return "Pepe's"
    if "rio" in name: return "Rio's"
    if "maeme" in name: return "Maeme's"
    if "grillo" in name: return "Grillo's"
    if "galos" in name: return "Galo's"
    if "jojo" in name: return "Jojo's"
    if "grill peri" in name: return "Grill Peri Peri"
    return "Independent"

def engineer_brand_maturity():
    print("=== TASK 8.3: BRAND & MATURITY ENGINEERING ===\n")
    
    if not os.path.exists(MASTER_CSV):
        print(f"Error: {MASTER_CSV} not found.")
        return

    # 1. Backup
    print("Step 1: Backup...")
    shutil.copy2(MASTER_CSV, BACKUP_CSV)
    print(f"  Backup created: {BACKUP_CSV}")

    # 2. Load
    print("Step 2: Loading Master Dataset...")
    df = pd.read_csv(MASTER_CSV, low_memory=False)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # 3. Inferred Brand
    print("Step 3: Extracting Inferred Brand...")
    df['Inferred_Brand'] = df['Branch Name'].apply(extract_brand)
    print(f"  Brand distribution:\n{df['Inferred_Brand'].value_counts()}")

    # 4. Days Since Open (Maturity)
    print("\nStep 4: Calculating Days Since Open (Relative to First Non-Zero Sale)...")
    
    # Group by Branch and Postcode
    grouped = df.sort_values('Date').groupby(['Branch Name', 'postcode'])
    
    def calc_maturity(group):
        # Find first non-zero sale
        non_zero_sales = group[group['Total Sale'] > 0]
        if not non_zero_sales.empty:
            first_date = non_zero_sales['Date'].min()
            maturity = (group['Date'] - first_date).dt.days
            # Rows before first sale are 0 (not yet mature)
            maturity = maturity.clip(lower=0)
            return maturity
        else:
            # If no non-zero sales ever, maturity is 0
            return pd.Series(0, index=group.index)

    df['Days_Since_Open'] = grouped.apply(lambda x: calc_maturity(x)).reset_index(level=[0,1], drop=True)
    
    # Sort back to original or standard order
    df = df.sort_values(['Branch Name', 'postcode', 'Date'])

    # 5. Save
    print("\nStep 5: Saving Master Dataset...")
    df.to_csv(MASTER_CSV, index=False)
    print(f"  Successfully saved {len(df)} rows.")

    # 6. Verification
    print("\nStep 6: Final Verification...")
    print(f"Maturity Stats:\n{df['Days_Since_Open'].describe()}")
    
    # Sample check for a known branch
    sample_branch = df[df['Branch Name'].str.contains('small heath', case=False)].sort_values('Date')
    if not sample_branch.empty:
        print(f"\nSample Maturity for Small Heath (B10 0UT):")
        print(sample_branch[['Date', 'Total Sale', 'Days_Since_Open']].head(10))

    if df['Days_Since_Open'].min() >= 0:
        print("\n[SUCCESS] Brand and Maturity features engineered perfectly.")
    else:
        print("\n[ERROR] Negative maturity values detected!")

if __name__ == "__main__":
    engineer_brand_maturity()
