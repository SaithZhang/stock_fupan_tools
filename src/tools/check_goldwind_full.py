import akshare as ak
import pandas as pd
import sys

# Encoding fix for Windows console
sys.stdout.reconfigure(encoding='utf-8')

pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', 10)
pd.set_option('display.width', 1000)

def check_stock(symbol="002202", date_str="20260109"):
    with open('debug_goldwind_full.txt', 'w', encoding='utf-8') as f:
        f.write(f"Checking {symbol} for {date_str}...\n")
        try:
            df = ak.stock_lhb_stock_detail_em(symbol=symbol, date=date_str)
            if not df.empty:
                cols = ['交易营业部名称', '买入金额', '卖出金额']
                # Ensure columns exist
                existing_cols = [c for c in cols if c in df.columns]
                
                df_view = df[existing_cols].copy()
                if '买入金额' in df_view.columns:
                     df_view['买入金额'] = pd.to_numeric(df_view['买入金额'], errors='coerce')
                     df_view = df_view.sort_values(by='买入金额', ascending=False)
                
                f.write(df_view.to_string())
            else:
                f.write("No data.")
        except Exception as e:
            f.write(f"Error: {e}")

if __name__ == "__main__":
    check_stock()
