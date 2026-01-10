import akshare as ak
import pandas as pd
from datetime import datetime

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def debug_detail():
    today = "20260108"
    code = "002413"
    print(f"--- Detail for {code} on {today} ---")
    
    # Attempt 1: stock_lhb_stock_detail_date_em (No Date Arg?)
    try:
        print("Testing stock_lhb_stock_detail_date_em(symbol Only)...")
        df = ak.stock_lhb_stock_detail_date_em(symbol=code)
        if not df.empty:
            print("Success (EM No Date)!")
            print("Columns:", df.columns.tolist())
            print(df.head())
            
            # Filter by date if needed
            if '交易日' in df.columns:
                 print("Filtering for today...")
                 # date fmt?
                 pass
            # return # Don't return, keep trying
    except Exception as e:
        print(f"Failed (EM No Date): {e}")

    # Attempt 3: stock_lhb_stock_detail_em (No Date)
    try:
        print("\nTesting stock_lhb_stock_detail_em(symbol Only)...")
        # May return dataframe with '交易日' column?
        df = ak.stock_lhb_stock_detail_em(symbol=code, date=today) 
        # Wait, if `date` failed before, try without date if supported, 
        # BUT search result said it provides detailed info.
        # Let's try matching what akshare typically does: valid symbol, date might be string '20260108'.
        
        # Actually my previous failure for `stock_lhb_stock_detail_em` was NOT run seeing the log.
        # It was skipped because return.
        pass
    except Exception as e:
        pass
        
    try:
        print("\nAttempt 3: stock_lhb_stock_detail_em(symbol, date)...")
        df = ak.stock_lhb_stock_detail_em(symbol=code, date=today)
        if not df.empty:
            print("Success (EM Detail)!")
            print("Columns:", df.columns.tolist())
            print(df.head())
            return
    except Exception as e:
        print(f"Failed (EM Detail): {e}")

if __name__ == "__main__":
    debug_detail()
