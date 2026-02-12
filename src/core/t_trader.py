# ==============================================================================
# 📈 做T/盘中辅助系统 (src/core/t_trader.py)
# Description: 计算个股支撑/压力位、异动监管风险、趋势状态
# ==============================================================================

import pandas as pd
import numpy as np
import datetime
from colorama import Fore
from src.data.tushare_source.client import TushareClient


class TTraderAssistant:
    def __init__(self):
        self.pro = TushareClient.get_pro()
        self.today = datetime.datetime.now().strftime('%Y%m%d')

    def analyze(self, ts_code: str, current_price: float = None):
        """
        核心分析入口
        :param ts_code: 股票代码
        :param current_price: 当前价格 (可选，如果不传则取最近收盘价)
        :return: 包含做T建议的字典
        """
        try:
            # 1. 获取日线数据 (过去30个交易日，用于趋势和监管计算)
            end_date = self.today
            start_date = (datetime.datetime.now() - datetime.timedelta(days=45)).strftime('%Y%m%d')

            df_daily = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df_daily.empty:
                return {}

            # 按日期正序排列
            df_daily = df_daily.sort_values('trade_date').reset_index(drop=True)

            # 基础数据准备
            latest = df_daily.iloc[-1]
            curr_p = current_price if current_price else latest['close']

            # --- 模块 A: 趋势与均线分析 ---
            ma5 = df_daily['close'].rolling(5).mean().iloc[-1]
            ma10 = df_daily['close'].rolling(10).mean().iloc[-1]

            trend_status = "🟢 上升"
            if curr_p < ma5:
                trend_status = "🔴 破位(线下)"
            elif curr_p < ma10:
                trend_status = "⚠️ 弱势"

            # --- 模块 B: 严重异动监管风险 (10日100% / 30日200%) ---
            # 简单估算：取10个交易日前的收盘价对比
            risk_warning = "无"
            if len(df_daily) >= 11:
                close_10_ago = df_daily.iloc[-11]['close']  # 10天前
                pct_10_days = (curr_p - close_10_ago) / close_10_ago

                if pct_10_days > 0.90:  # 涨幅超过90%，接近100%红线
                    risk_warning = f"🔥 严重异动预警 (10日涨幅 {pct_10_days * 100:.1f}%)"
                elif pct_10_days > 0.7:
                    risk_warning = f"⚠️ 监管关注区 (10日涨幅 {pct_10_days * 100:.1f}%)"

            # --- 模块 C: 筹码支撑/压力 (基于分钟数据) ---
            # 注意：分钟数据拉取较慢，仅对入池标的执行
            support_level, resistance_level = self._calc_intraday_levels(ts_code)

            # 修正支撑位：取 MA5 和 筹码密集区 的较高值 (防守线)
            final_support = max(ma5, support_level) if support_level else ma5

            # --- 模块 D: 生成做T建议 ---
            action_signal = "观望"
            t_gap = 0.0  # 预期做T空间

            if resistance_level > 0:
                t_gap = (resistance_level - final_support) / final_support * 100

            if curr_p < final_support * 1.01 and trend_status != "🔴 破位(线下)":
                action_signal = "🛒 关注低吸 (回踩支撑)"
            elif resistance_level > 0 and curr_p > resistance_level * 0.99:
                action_signal = "💰 建议高抛 (主要压力)"

            return {
                't_trend': trend_status,
                't_ma5': round(ma5, 2),
                't_support': round(final_support, 2),
                't_pressure': round(resistance_level, 2) if resistance_level else 0,
                't_risk': risk_warning,
                't_signal': action_signal,
                't_space': f"{t_gap:.1f}%"  # 做T空间
            }

        except Exception as e:
            print(f"{Fore.RED}做T分析出错 {ts_code}: {e}")
            return {}

    def _calc_intraday_levels(self, ts_code):
        """
        计算分钟级别的支撑压力 (利用最近5个交易日的60分钟K线)
        """
        try:
            # 减少请求量，只取最近5天
            end_dt = datetime.datetime.now()
            start_dt = end_dt - datetime.timedelta(days=7)

            df_min = self.pro.stk_mins(
                ts_code=ts_code,
                freq='60min',
                start_date=start_dt.strftime('%Y-%m-%d 09:00:00'),
                end_date=end_dt.strftime('%Y-%m-%d 15:00:00')
            )

            if df_min.empty:
                return 0, 0

            # 1. 压力位：取近期最高价
            recent_high = df_min['high'].max()

            # 2. 支撑位：简化版筹码峰 (Volume Profile)
            # 将价格切分为20个区间，看哪个区间成交量最大
            price_bins = pd.cut(df_min['close'], bins=20)
            vol_profile = df_min.groupby(price_bins, observed=False)['vol'].sum()

            if not vol_profile.empty:
                max_vol_bin = vol_profile.idxmax()
                chip_support = (max_vol_bin.left + max_vol_bin.right) / 2
            else:
                chip_support = df_min['close'].mean()

            return chip_support, recent_high

        except Exception:
            return 0, 0