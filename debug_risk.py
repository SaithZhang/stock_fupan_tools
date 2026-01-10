import akshare as ak
import pandas as pd

# 000547 航天发展
code = "000547"
target_dev = 191.03

def fetch_data():
    print(f"Fetching {code}...")
    s_df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").sort_values('日期', ascending=False).head(100)
    s_df['date'] = s_df['日期'].astype(str)
    
    indices = {}
    for sym in ["sz399001", "sz399106", "sz399107"]:
        print(f"Fetching {sym}...")
        try:
            df = ak.stock_zh_index_daily_em(symbol=sym).sort_values('date', ascending=False).head(100)
            df['date'] = df['date'].astype(str)
            indices[sym] = df
        except:
            print(f"Failed {sym}")
            
    return s_df, indices

stock_df, indices = fetch_data()

print(f"\nScanning for Deviation ~{target_dev}%...")

for name, i_df in indices.items():
    print(f"\n--- Checking Index {name} ---")
    for d in range(10, 60):
        # Alignment
        common = list(set(stock_df['date']) & set(i_df['date']))
        common.sort(reverse=True)
        
        if len(common) <= d: continue
        
        curr = common[0] # Today
        start = common[d] # T-d
        
        try:
            s_curr = float(stock_df[stock_df['date'] == curr]['收盘'].iloc[0])
            s_start = float(stock_df[stock_df['date'] == start]['收盘'].iloc[0])
            
            i_curr = float(i_df[i_df['date'] == curr]['close'].iloc[0])
            i_start = float(i_df[i_df['date'] == start]['close'].iloc[0])
            
            s_gain = (s_curr - s_start) / s_start
            i_gain = (i_curr - i_start) / i_start
            
            dev = (s_gain - i_gain) * 100
            
            if abs(dev - target_dev) < 5.0:
                print(f"MATCH! Days: {d} (Start: {start}) | Dev: {dev:.2f}% | Price: {s_curr}/{s_start} | Idx: {i_curr}/{i_start}")
                
        except:
            pass
