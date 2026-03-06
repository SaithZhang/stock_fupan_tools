# src/data/tushare_source/steps/trend.py

import pandas as pd
import re
from colorama import Fore
from .base import BaseDataStep


class TrendAndDragonStep(BaseDataStep):
    """[P_New] 趋势与老龙特征分析 (计算15日回撤、MA10、断板天数等)"""

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[X/?]"
        print(f"   ├── {prefix} 计算老龙形态与均线(15日窗口)...", end="", flush=True)

        try:
            # 1. 获取过去 15 个交易日的日历
            cal = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=15)
            dates = cal['cal_date'].tolist()
            dates.sort()  # 按时间正序：[T-14, ..., T-1, T]

            if not dates:
                print(f" {Fore.RED}❌ 日历获取失败{Fore.RESET}")
                return

            start_date = dates[0]

            # 2. 批量拉取这 15 天的 Daily 数据 (全市场一次性拉回，大约 7.5万 行，Pandas处理极快)
            df_daily = self.pro.daily(start_date=start_date, end_date=date_str, fields='ts_code,trade_date,close,high')

            if df_daily.empty:
                print(f" {Fore.YELLOW}⚠️ 日线数据为空{Fore.RESET}")
                return

            # --- 计算 MA10 和 区间最大回撤 ---
            # 获取近10天的日期范围用于算MA10
            dates_10 = set(dates[-10:])
            df_10 = df_daily[df_daily['trade_date'].isin(dates_10)]

            # 计算 MA10
            ma10_s = df_10.groupby('ts_code')['close'].mean()

            # 计算 15日最高价 和 最新收盘价
            high_15_s = df_daily.groupby('ts_code')['high'].max()
            # 取最后一天的收盘价
            latest_close_s = df_daily[df_daily['trade_date'] == date_str].set_index('ts_code')['close']

            # 计算回撤 % = (最新价 - 15日最高) / 15日最高 * 100 (负数表示跌幅)
            drawdown_s = (latest_close_s - high_15_s) / high_15_s * 100

            # 3. 批量拉取这 15 天的涨停数据 (循环15次API，耗时极短)
            zt_history = []
            for d in dates:
                try:
                    df_zt = self.pro.limit_list_ths(trade_date=d, limit_type='涨停池', fields='ts_code,tag')
                    if not df_zt.empty:
                        df_zt['trade_date'] = d
                        zt_history.append(df_zt)
                except:
                    pass

            # --- 计算最大连板数 和 断板天数 ---
            max_boards = {}
            last_zt_date = {}

            if zt_history:
                df_all_zt = pd.concat(zt_history)
                # 遍历每只曾涨停的票
                for ts_code, group in df_all_zt.groupby('ts_code'):
                    # 算最近一次涨停距离今天(dates[-1])几天
                    last_zt = group['trade_date'].max()
                    days_since = dates.index(dates[-1]) - dates.index(last_zt)
                    last_zt_date[ts_code] = days_since

                    # 算最大连板数 (解析 tag，如 '3连板' -> 3，首板 -> 1)
                    mb = 1
                    for tag in group['tag'].dropna():
                        m = re.search(r'(\d+)(连板|板)', str(tag))
                        if m:
                            mb = max(mb, int(m.group(1)))
                    max_boards[ts_code] = mb

            # 4. 把计算结果存入上下文，供 enrich 阶段使用
            context['trend_data'] = {
                'ma10': ma10_s.to_dict(),
                'drawdown': drawdown_s.to_dict(),
                'max_boards': max_boards,
                'days_since_zt': last_zt_date
            }

            print(f" ✅")

        except Exception as e:
            print(f" {Fore.RED}❌ 异常: {e}{Fore.RESET}")

    def enrich(self, stock, row, context):
        """将计算好的特征挂载到 stock 对象或 item 字典上"""
        trend_data = context.get('trend_data', {})
        if not trend_data:
            return

        ts_code = stock.ts_code

        # 挂载到 stock 对象上 (由于 Tagger 取的是 item_dict，我们放到对象属性里)
        stock.ma10 = trend_data.get('ma10', {}).get(ts_code, 0.0)

        # 回撤如果是正数或没数据，设为绝对值
        dd = trend_data.get('drawdown', {}).get(ts_code, 0.0)
        stock.drawdown_from_high = abs(dd) if pd.notna(dd) else 100.0

        stock.recent_max_boards = trend_data.get('max_boards', {}).get(ts_code, 0)

        # 如果没有涨停过，设为一个极大值(比如 99天)
        stock.days_since_last_zt = trend_data.get('days_since_zt', {}).get(ts_code, 99)