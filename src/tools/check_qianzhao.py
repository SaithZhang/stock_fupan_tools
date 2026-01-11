import akshare as ak
import pandas as pd
import sys

# Encoding fix
sys.stdout.reconfigure(encoding='utf-8')

def check_stock(symbol="300102"):
    with open('debug_qianzhao_full.txt', 'w', encoding='utf-8') as f:
        dates = ["20260109", "20260108"]
        for d in dates:
            f.write(f"--- Checking {symbol} for {d} ---\n")
            try:
                df = ak.stock_lhb_stock_detail_em(symbol=symbol, date=d)
                if not df.empty:
                    if '买入金额' in df.columns:
                         df['买入金额'] = pd.to_numeric(df['买入金额'], errors='coerce')
                         df = df.sort_values(by='买入金额', ascending=False)
                    
                    f.write(df[['交易营业部名称', '买入金额', '卖出金额']].to_string())
                    f.write("\n\n")
                else:
                    f.write("No data.\n")
            except Exception as e:
                f.write(f"Error: {e}\n")

if __name__ == "__main__":
    check_stock()
