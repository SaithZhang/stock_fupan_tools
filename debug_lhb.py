import akshare as ak
import pandas as pd
from datetime import datetime

# 设置显示所有列
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def test_lhb():
    today = datetime.now().strftime("%Y%m%d")
    print(f"Fetching LHB data for {today}...")
    
    try:
        # stock_lhb_detail_em: 龙虎榜详情
        # data = ak.stock_lhb_detail_em(start_date=today, end_date=today)
        
        # stock_lhb_detail_daily_sina: 新浪龙虎榜
        # data = ak.stock_lhb_detail_daily_sina(date=today)
        
        # stock_lhb_jgmx_sina: 机构席位追踪
        
        # Let's try EastMoney as it's usually stable
        # ak.stock_lhb_detail_em(date="20240108") 
        # Checking akshare documentation (mental model): stock_lhb_detail_em takes start_date and end_date
        
        df = ak.stock_lhb_detail_em(start_date=today, end_date=today)
        
        if df.empty:
            print("No data returned. Converting to yesterday for testing if today is empty.")
            # fallback to a recent trading day just in case
            df = ak.stock_lhb_detail_em(start_date="20260107", end_date="20260107")
            
        if not df.empty:
            print("\nColumns:", df.columns.tolist())
            print(df.head())
            
            # Check distinct stocks
            print("\nUnique Codes:", len(df['代码'].unique()))
            
            # Check what kind of data we have
            # Usually implies Buying/Selling seats
        else:
            print("Still no data.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_lhb()
