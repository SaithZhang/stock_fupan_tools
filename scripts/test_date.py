import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def get_latest_trade_date():
    try:
        # fetch trade dates
        df = ak.tool_trade_date_hist_sina()
        # df has column 'trade_date' as datetime.date usually
        
        # Ensure it is datetime
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        today = datetime.now().date()
        
        # Filter for dates <= today
        past_dates = df[df['trade_date'].dt.date <= today]
        
        if past_dates.empty:
            print("No past dates found?")
            return None
            
        latest = past_dates.iloc[-1]['trade_date'].date()
        print(f"Today: {today}")
        print(f"Latest Trade Date: {latest}")
        
        # Check specific case: if today is Sunday, does it return Friday?
        # Simulation:
        sim_sunday = pd.Timestamp("2024-06-23").date() # A known Sunday
        sim_past = df[df['trade_date'].dt.date <= sim_sunday]
        print(f"Simanulated Sunday {sim_sunday} -> {sim_past.iloc[-1]['trade_date'].date()}")
        
        return latest
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_latest_trade_date()
