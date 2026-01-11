import akshare as ak
import pandas as pd
import time

def check_indices():
    print("--- Indices ---")
    try:
        # 实时指数: 000001(上证), 399001(深证), 399006(创业板)
        # ak.stock_zh_index_spot() 返回所有指数
        df = ak.stock_zh_index_spot()
        # Filter for key indices
        # 上证指数 code might be sh000001 or just 000001
        
        # Akshare index codes in spot usually: 
        # sh000001 = 上证指数
        # sz399001 = 深证成指
        # sz399006 = 创业板指
        
        target_codes = ['sh000001', 'sz399001', 'sz399006', 'sh000300'] # 沪深300
        interest = df[df['代码'].isin(target_codes)]
        print(interest)
    except Exception as e:
        print(f"Error fetching indices: {e}")

def check_northbound():
    print("\n--- Northbound Funds (Bei Xiang) ---")
    try:
        # 东方财富-数据中心-沪深港通持股-北向资金-每日资金流向
        # ak.stock_hsgt_north_net_flow_in_em() ? 
        # Or: stock_hsgt_north_cash_flow_in_em ? (Funds inflow)
        # Actually usually we want the realtime flow.
        # ak.stock_hsgt_north_net_flow_in_em is usually historical/daily?
        
        # Realtime:
        # items = ak.stock_hsgt_north_money_flow_in_em()  # ❌ Deprecated maybe?
        
        # stock_hsgt_north_cash_flow_in_em fetches historical
        
        # Let's try: stock_hsgt_north_spot_em() ?
        # Or stock_em_hsgt_north_net_flow_in using ak.stock_hsgt_north_net_flow_in_em()
        pass 
        
        # Trying a likely one for realtime net inflow:
        # stock_hsgt_north_net_flow_in_em
        
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="沪股通")
        print("沪股通 (Latest):")
        print(df.tail(1))
        
        df2 = ak.stock_hsgt_north_net_flow_in_em(symbol="深股通")
        print("深股通 (Latest):")
        print(df2.tail(1))
        
        # If this is history, we need realtime.
        # Maybe: ak.stock_hsgt_north_cash_flow_in_em() is for specific day?
        
    except Exception as e:
        print(f"Error fetching northbound: {e}")

def check_total_volume():
    print("\n--- Total Volume ---")
    try:
        df = ak.stock_zh_a_spot_em()
        total_amt = df['成交额'].sum()
        print(f"Total A-share Turnover: {total_amt/100000000:.2f} 亿")
    except Exception as e:
        print(f"Error fetching total volume: {e}")

if __name__ == "__main__":
    check_indices()
    check_total_volume()
    check_northbound()
