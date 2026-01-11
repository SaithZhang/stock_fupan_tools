import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def check_stock(symbol="002202"):
    print(f"Checking {symbol}...")
    
    for i in range(5):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        print(f"--- Date: {date_str} ---")
        try:
            df = ak.stock_lhb_stock_detail_em(symbol=symbol, date=date_str)
            if not df.empty:
                print("Columns:", df.columns.tolist())
                print(df.head(10).to_string())
                return
            else:
                print("No data.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_stock()
