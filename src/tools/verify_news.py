import akshare as ak
import pandas as pd
import sys

# Encoding fix
sys.stdout.reconfigure(encoding='utf-8')
pd.set_option('display.max_rows', 1000)
pd.set_option('display.width', 1000)

def verify_news():
    # 1. Qianzhao Optoelectronics (300102) - Check for Brother Yu (Soochow Xiangcheng)
    print("\n=== Qianzhao Optoelectronics (300102) 20260109 ===")
    try:
        # Note: Akshare might return multiple lists (Daily, 3-Day) if they exist. 
        # Usually it returns all rows combined or distinct entries.
        df = ak.stock_lhb_stock_detail_em(symbol="300102", date="20260109")
        if not df.empty:
            print(df[['交易营业部名称', '买入金额', '卖出金额', '类型']].to_string())
        else:
            print("No data found.")
    except Exception as e:
        print(f"Error 300102: {e}")

    # 2. Aerospace Electronic (600879) - Check for Xiaoxianpai (Yichang Yanjiang)
    print("\n=== Aerospace Electronic (600879) 20260109 ===")
    try:
        df = ak.stock_lhb_stock_detail_em(symbol="600879", date="20260109")
        if not df.empty:
            print(df[['交易营业部名称', '买入金额', '卖出金额']].to_string())
        else:
            print("No data found.")
    except Exception as e:
        print(f"Error 600879: {e}")
        
    # 3. Goldwind (002202) - Check for Zhongshan East Road
    print("\n=== Goldwind (002202) 20260109 ===")
    try:
        df = ak.stock_lhb_stock_detail_em(symbol="002202", date="20260109")
        if not df.empty:
            print(df[['交易营业部名称', '买入金额', '卖出金额']].to_string())
    except Exception as e:
        print(e)

if __name__ == "__main__":
    verify_news()
