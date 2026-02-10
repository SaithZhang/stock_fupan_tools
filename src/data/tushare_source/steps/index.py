# src/data/tushare_source/steps/index.py
from colorama import Fore

class MarketIndexStep:
    """
    [独立功能] 获取大盘指数数据 (上证、深证、创业板等)
    这不是流水线的一部分，而是独立的全局数据获取
    """
    def __init__(self, pro):
        self.pro = pro

    def fetch_index_data(self, date_str):
        print(f"   📊 正在获取大盘指数...", end="")
        targets = {'sh': '000001.SH', 'sz': '399001.SZ', 'gz': '399303.SZ'}
        result = {}
        try:
            for k, c in targets.items():
                df = self.pro.index_daily(ts_code=c, trade_date=date_str)
                if not df.empty:
                    result[k] = {
                        'pct': float(df.iloc[0]['pct_chg']),
                        'amount': float(df.iloc[0]['amount']) * 1000
                    }
            print(" ✅")
            return result
        except Exception as e:
            print(f" {Fore.RED}❌ 获取指数失败: {e}{Fore.RESET}")
            return {}