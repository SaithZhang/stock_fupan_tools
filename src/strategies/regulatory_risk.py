# src/strategies/regulatory_risk.py

import akshare as ak
import pandas as pd
import datetime
from colorama import Fore, Style
import time

class RegulatoryCalculator:
    def __init__(self):
        # Cache for index data to avoid repeated fetching
        self.index_cache = {}
        self.stock_cache = {}
        
        # Benchmark Index Mapping (Prefixed for akshare)
        # SZ: 399107 (Shenzhen A-Share) is the standard for deviation, not Component (399001) or Composite (399106)
        # SH: 000001 (Shanghai Composite)
        self.BENCHMARKS = {
            'sh': 'sh000001',     # Shanghai Composite
            'sz': 'sz399107',     # Shenzhen A-Share Index (Regulatory Standard)
            'sz_cy': 'sz399006',  # ChiNext Index
            'kc': 'sh000688',     # STAR 50 
            'bj': 'bj899050',     # Beijing 50
        }

    def get_market_type(self, code):
        """Determine market type to select benchmark"""
        if code.startswith('688'): return 'kc'
        if code.startswith('6'): return 'sh'
        if code.startswith('30'): return 'sz_cy'
        if code.startswith('00'): return 'sz'
        if code.startswith(('8', '4')): return 'bj'
        return 'sh' # Default

    def fetch_history(self, code, is_index=False, days=60):
        """Fetch historical data (cached)"""
        if is_index:
            if code in self.index_cache: return self.index_cache[code]
            try:
                # Use akshare for index history
                df = ak.stock_zh_index_daily_em(symbol=code)
                df = df.sort_values('date', ascending=False).head(days)
                # Normalize columns
                df = df[['date', 'close']]
                df['date'] = df['date'].astype(str)
                self.index_cache[code] = df
                return df
            except Exception as e:
                print(f"Error fetching index {code}: {e}")
                return pd.DataFrame()
        else:
            # For stocks, we assume we might need to fetch if not passed in
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                df = df.sort_values('日期', ascending=False).head(days)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
                df['date'] = df['date'].astype(str)
                return df
            except:
                return pd.DataFrame()

    def calculate_period_deviation(self, df_stock, df_index, days):
        """
        Calculate deviation for a specific window (e.g., 10 days).
        Formula: (Stock_End / Stock_Start - 1) - (Index_End / Index_Start - 1)
        Note: strictly, it's usually T vs T-days.
        """
        if len(df_stock) <= days or len(df_index) <= days:
            return 0.0, 0.0

        # Align dates (Intersection)
        common_dates = list(set(df_stock['date']) & set(df_index['date']))
        common_dates.sort(reverse=True)
        
        if len(common_dates) <= days:
            return 0.0, 0.0
            
        current_date = common_dates[0]
        start_date = common_dates[days] # T-days ago
        
        def get_close(df, d):
            rows = df[df['date'] == d]
            if not rows.empty: return float(rows.iloc[0]['close'])
            return None

        s_curr = get_close(df_stock, current_date)
        s_start = get_close(df_stock, start_date)
        
        i_curr = get_close(df_index, current_date)
        i_start = get_close(df_index, start_date)
        
        if s_curr and s_start and i_curr and i_start:
            stock_rise = (s_curr - s_start) / s_start
            index_rise = (i_curr - i_start) / i_start
            deviation = (stock_rise - index_rise) * 100
            return deviation, s_curr
            
        return 0.0, 0.0

    def calculate_trigger_price(self, df_stock, df_index, days, threshold_pct):
        """
        Calculate next day trigger price.
        Let P_next be stock price tomorrow.
        Stock_Rise_New = (P_next - P_start) / P_start
        Index_Rise_New (Assume 0% change for index tomorrow as conservative est) = (I_curr - I_start) / I_start
        
        Deviation_New = Stock_Rise_New - Index_Rise_New = Threshold
        => Stock_Rise_New = Threshold + Index_Rise_New
        => (P_next / P_start) - 1 = Threshold/100 + Index_Rise
        => P_next = P_start * (1 + Threshold/100 + Index_Rise)
        """
        if len(df_stock) < days or len(df_index) < days: return 0.0
        
        common_dates = list(set(df_stock['date']) & set(df_index['date']))
        common_dates.sort(reverse=True)
        
        if len(common_dates) < days: return 0.0
        
        # For "Next Day" trigger, the start date shifts by one? 
        # Usually checking "Today + past 9 days" (10 days total)
        # Tomorrow it will be "Tomorrow + Today + past 8 days".
        # So the base price is effectively common_dates[days-1].
        
        start_date = common_dates[days-1] 
        
        def get_close(df, d):
            rows = df[df['date'] == d]
            if not rows.empty: return float(rows.iloc[0]['close'])
            return None

        s_start = get_close(df_stock, start_date)
        i_curr = get_close(df_index, common_dates[0])
        i_start = get_close(df_index, start_date)
        
        if s_start and i_curr and i_start:
            index_rise = (i_curr - i_start) / i_start
            # Target Deviation = threshold
            # (Stock_Rise - Index_Rise) * 100 = threshold
            # Stock_Rise = threshold/100 + Index_Rise
            target_stock_rise = (threshold_pct / 100.0) + index_rise
            
            p_next = s_start * (1 + target_stock_rise)
            return p_next
            
        return 0.0

    def analyze_risk(self, code, current_price):
        """
        Analyze risk for a single stock.
        Scans windows from 10 to 32 days to find the specific regulation trigger.
        Returns the scenario with the highest Risk Ratio (Current Deviation / Threshold).
        """
        mtype = self.get_market_type(code)
        idx_code = self.BENCHMARKS.get(mtype)
        if not idx_code: return {}
        
        df_index = self.fetch_history(idx_code, is_index=True, days=60)
        df_stock = self.fetch_history(code, is_index=False, days=60)
        
        if df_stock.empty or df_index.empty: return {}
        
        best_scenario = {
            'risk_level': '🟢 Safe',
            'msg': 'Safe',
            'risk_ratio': 0.0,
            'trigger_ratio': 999.0,
            'rule_name': ''
        }
        
        # Scan windows to match "KaiPanLa" logic (finding the worst window)
        # 10 days rule: 100% limit
        # 30 days rule: 200% limit
        # Often checking range [10, 32] covers offsets/holidays
        
        for d in range(10, 33):
            dev, _ = self.calculate_period_deviation(df_stock, df_index, d)
            
            # Determine threshold
            threshold = 200.0
            rule_name = f"{d}日200%"
            
            if d <= 10:
                threshold = 100.0
                rule_name = f"{d}日100%"
            
            # Risk Ratio: How close are we?
            risk_ratio = dev / threshold
            
            # Level
            level = "🟢 Safe"
            if risk_ratio > 0.9: level = "🔴 High"     # >90% of threshold
            elif risk_ratio > 0.8: level = "🟠 Med"    # >80% of threshold
            
            # Keep the detailed message if it's dangerous
            if risk_ratio > best_scenario['risk_ratio']:
                # Calculate trigger for this specific window
                trig_price = self.calculate_trigger_price(df_stock, df_index, d, threshold)
                if trig_price > 0:
                    trig_ratio = (trig_price - current_price) / current_price * 100
                else:
                    trig_ratio = 999.0
                
                best_scenario = {
                    'risk_level': level,
                    'msg': f"{d}日{dev:.1f}%",
                    'risk_ratio': risk_ratio,
                    'trigger_ratio': trig_ratio,
                    'rule_name': rule_name
                }
        
        return best_scenario

if __name__ == "__main__":
    # Test
    calc = RegulatoryCalculator()
    print("Testing with 601127 (Example)...")
    res = calc.analyze_risk("601127", 35.0) # Mock price
    print(res)
