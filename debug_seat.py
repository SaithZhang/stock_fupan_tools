import akshare as ak
import pandas as pd
from datetime import datetime

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def debug_columns():
    today = "20260108"
    print(f"Fetching Active Branch data for {today}...")
    try:
        df = ak.stock_lhb_hyyyb_em(start_date=today, end_date=today)
        if not df.empty:
            print("Columns:")
            for c in df.columns:
                print(f" - {c}")
            
    print("\n--- Detail for 002413 (Leike) ---")
    try:
        df_detail = ak.stock_lhb_ggmx_em(symbol="002413", date=today)
        if not df_detail.empty:
            print(df_detail)
        else:
            print("No detail for 002413")
    except Exception as e:
        print(f"Error fetching detail: {e}")

if __name__ == "__main__":
    debug_columns()
