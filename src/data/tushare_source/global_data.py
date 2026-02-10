# src/data/tushare_source/global_data.py
import pandas as pd
from colorama import Fore
from src.data.tushare_source.client import TushareClient
from src.data.tushare_source.steps.limit import LimitBoardStep


class MarketOverview:
    """
    🌍 [大盘全景] 专门负责宏观数据
    包括：指数涨跌、涨跌停家数、连板高度等
    """

    def __init__(self):
        self.pro = TushareClient.get_pro()

    def fetch_index(self, date_str) -> dict:
        """获取大盘指数 (上证/深证/创业板)"""
        if not self.pro: return {}
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
        except:
            print(f" {Fore.RED}❌{Fore.RESET}")
            return {}

    def fetch_limit_stats(self, date_str):
        """获取涨跌停统计 (复用 LimitStep 的能力)"""
        # 我们复用 LimitBoardStep 的逻辑来获取数据，但不做 Enrich
        step = LimitBoardStep(self.pro)
        ctx = {}
        # 复用 fetch 逻辑
        step.fetch(date_str, ctx)

        # 统计结果
        count_up = len(ctx.get('zt_codes', []))
        # 这里只返回统计数据，不返回 DataFrame
        return {'limit_up_count': count_up}