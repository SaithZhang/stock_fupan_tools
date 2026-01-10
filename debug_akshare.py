import akshare as ak
import pandas as pd

symbols = ['sh000001', '000001', 'sz399001', '399001', 'sh000688', 'sz399006', 'bj899050']

for s in symbols:
    print(f"Testing {s}...")
    try:
        df = ak.stock_zh_index_daily_em(symbol=s)
        if not df.empty:
            print(f"Success! Columns: {df.columns.tolist()}")
            print(df.head(1))
        else:
            print("Empty DataFrame")
    except Exception as e:
        print(f"Error: {e}")
