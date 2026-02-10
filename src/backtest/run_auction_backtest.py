# ==============================================================================
# 🔙 竞价策略回测系统 (src/backtest/run_auction_backtest.py)
# Version: 2.0 (With Broken Board Detection)
# ==============================================================================

import os
import sys
import pandas as pd
import numpy as np
from colorama import init, Fore

# 环境设置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([project_root, os.path.join(project_root, 'src')])

try:
    from src.data.tushare_source.client import TushareClient
    from src.strategies.auction import AuctionStrategy
except ImportError as e:
    print(f"❌ 模块加载失败: {e}")
    sys.exit(1)

init(autoreset=True)


class AuctionBacktest:
    def __init__(self, start_date, end_date):
        self.pro = TushareClient.get_pro()
        self.start_date = start_date
        self.end_date = end_date
        self.analyzer = AuctionStrategy()
        self.results = []
        self.trade_cal = []

    def load_data(self):
        """加载交易日历"""
        df = self.pro.trade_cal(exchange='', is_open='1', start_date=self.start_date, end_date=self.end_date)
        self.trade_cal = df['cal_date'].tolist()
        print(f"📅 回测区间: {self.start_date} ~ {self.end_date} (共 {len(self.trade_cal)} 天)")

    def calculate_limit_price(self, row):
        """简易计算涨停价 (用于判断炸板)"""
        # 简单处理：非科创/创业板 10%，科创/创业 20%
        # 严谨回测需要用 st_limit 接口，这里为了速度做估算
        factor = 1.20 if row['ts_code'].startswith(('300', '688')) else 1.10
        # 简单四舍五入到分，实际需要 round(x, 2)
        return round(row['pre_close'] * factor, 2)

    def run(self):
        self.load_data()

        for idx, date_str in enumerate(self.trade_cal):
            print(f"[{idx + 1}/{len(self.trade_cal)}] 回测: {date_str} ...", end="")

            # 1. 获取数据 (T日竞价 + T-1日行情)
            try:
                # 获取 T 日竞价
                df_auc = self.pro.stk_auction(trade_date=date_str)
                if df_auc.empty:
                    print(" 无竞价数据 -> 跳过")
                    continue

                # 获取 T-1 日行情 (用于判断昨日强弱/炸板)
                prev_dates = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)
                prev_date = prev_dates.iloc[0]['cal_date']
                df_prev = self.pro.daily(trade_date=prev_date)

                # 获取 T 日行情 (用于结算收益)
                df_daily = self.pro.daily(trade_date=date_str)

                # 合并数据
                # df_auc: T日竞价
                # df_prev: T-1日数据 (重命名为 yest_*)
                # df_daily: T日数据 (用于计算 open, close 收益)

                df_prev = df_prev.rename(columns={
                    'close': 'yest_close',
                    'high': 'yest_high',
                    'pct_chg': 'yest_pct',
                    'amount': 'yest_amt',
                    'pre_close': 'yest_pre_close'  # T-1的昨收，用于算涨停价
                })

                # Merge 1: Auction + Daily(Today)
                merged = pd.merge(df_auc, df_daily[['ts_code', 'open', 'close', 'high', 'low', 'pct_chg']],
                                  on='ts_code')
                # Merge 2: + Previous Day
                merged = pd.merge(merged, df_prev[
                    ['ts_code', 'yest_close', 'yest_high', 'yest_pct', 'yest_amt', 'yest_pre_close']], on='ts_code')

            except Exception as e:
                print(f" 数据获取错: {e}")
                continue

            # 2. 逐个分析
            daily_picks = []

            for _, row in merged.iterrows():
                # --- A. 数据准备 ---
                # 竞价涨幅
                price = float(row['price'])
                pre_close = float(row['pre_close'])  # T日的昨收
                if pre_close == 0: continue
                auc_pct = (price - pre_close) / pre_close * 100
                auc_amt = float(row['amount'])

                # 昨成交 (daily单位是千，auction是元，需统一)
                yest_amt = float(row['yest_amt']) * 1000
                ratio = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0

                # --- B. 炸板计算 (核心) ---
                # 如果 T-1 最高价 接近 涨停价，且收盘价 < 涨停价，视为炸板/烂板
                limit_up_price = self.calculate_limit_price(
                    {'ts_code': row['ts_code'], 'pre_close': row['yest_pre_close']})
                is_broken = False
                if row['yest_high'] >= limit_up_price * 0.99 and row['yest_close'] < limit_up_price * 0.98:
                    is_broken = True

                # --- C. 策略判定 ---
                ctx = {
                    'yest_pct': row['yest_pct'],
                    'is_broken': is_broken,
                    'yest_tag': "炸板" if is_broken else ""  # 模拟标签
                }

                decision, _ = self.analyzer.analyze(auc_pct, ratio, ctx)

                if "弱转强" in decision:
                    # 模拟交易: 开盘买入
                    open_price = row['open']
                    close_price = row['close']
                    high_price = row['high']

                    if open_price > 0:
                        profit = (close_price - open_price) / open_price * 100
                        max_profit = (high_price - open_price) / open_price * 100
                    else:
                        profit = 0;
                        max_profit = 0

                    daily_picks.append({
                        'date': date_str,
                        'code': row['ts_code'],
                        'decision': decision,
                        'auc_pct': auc_pct,
                        'auc_amt': auc_amt,
                        'profit': profit,
                        'max_profit': max_profit
                    })

            # 3. 每日优选 (模拟只买竞价金额最大的前3个)
            daily_picks.sort(key=lambda x: x['auc_amt'], reverse=True)
            top_picks = daily_picks[:3]
            self.results.extend(top_picks)

            avg_p = np.mean([p['profit'] for p in top_picks]) if top_picks else 0
            print(
                f" 选中 {len(top_picks)} 只 | 日均收益: {Fore.RED if avg_p > 0 else Fore.GREEN}{avg_p:.2f}%{Fore.RESET}")

    def report(self):
        if not self.results: return
        df = pd.DataFrame(self.results)
        print("\n" + "=" * 50)
        print(f"📊 回测总结 ({self.start_date} - {self.end_date})")
        print("=" * 50)
        print(f"总交易: {len(df)} 笔")
        print(f"胜率: {len(df[df['profit'] > 0]) / len(df) * 100:.1f}%")
        print(f"平均收益: {df['profit'].mean():.2f}% (收盘)")
        print(f"最大潜在收益: {df['max_profit'].mean():.2f}% (盘中摸高)")
        print("-" * 50)
        print("最佳交易:")
        print(df.sort_values('profit', ascending=False).head(3)[['date', 'code', 'decision', 'profit']])


if __name__ == "__main__":
    # 建议只测最近一周，因为竞价数据拉取较慢
    bt = AuctionBacktest(start_date='20260210', end_date='20260210')
    bt.run()
    bt.report()