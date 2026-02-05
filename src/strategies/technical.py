# ==============================================================================
# 📈 技术面策略 (src/strategies/technical.py)
# 包含：均线趋势、断板反包、DDD模式、焚诀模型、横盘筹码模型
# ==============================================================================

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from .base import BaseStrategy
from src.data.market import TechnicalAnalyzer

# 尝试导入外部独立策略文件
try:
    from src.strategies.ddd_mode import get_ddd_pool_category
    from src.strategies.f_lao_model import check_fen_jue
except ImportError:
    def get_ddd_pool_category(item):
        return None


    def check_fen_jue(df):
        return []


class TrendStrategy(BaseStrategy):
    """
    趋势策略：5日线低吸、趋势加速、死鱼潜伏
    """

    def __init__(self, history_map: Dict):
        self.history_map = history_map

    def run(self, item: Dict) -> List[str]:
        code = item['code']
        price = item.get('price', 0)
        if code not in self.history_map: return []

        tags, _ = TechnicalAnalyzer.calculate_indicators(self.history_map[code], price)

        final_tags = []
        for t in tags:
            if t == "🎯5日线低吸":
                final_tags.append("🎯5日线低吸(F佬推荐)")
            else:
                final_tags.append(t)

        f_tags = check_fen_jue(self.history_map[code])
        if f_tags: final_tags.extend(f_tags)

        return final_tags


class DDDStrategy(BaseStrategy):
    """
    DDD (大订单/特定模式) 策略
    """

    def run(self, item: Dict) -> List[str]:
        ddd_tag = get_ddd_pool_category(item)
        if ddd_tag: return [ddd_tag]
        return []


class ReboundStrategy(BaseStrategy):
    """
    反包策略：断板反包、跌停博弈
    """

    def __init__(self, broken_pool_map: Dict):
        self.broken_pool_map = broken_pool_map

    def run(self, item: Dict) -> List[str]:
        tags = []
        code = item['code']
        pct = item.get('today_pct', 0)
        raw_tag = str(item.get('tag', ''))

        if code in self.broken_pool_map and pct > 0:
            yest_amt = self.broken_pool_map[code]['amount']
            label = "🔥A大焚诀"
            if yest_amt > 10000 and item.get('amount', 0) > yest_amt:
                label += "/爆量"
            tags.append(label)

        if pct <= -9.0: tags.append("📉跌停/博弈修复")

        is_zb = "炸板" in raw_tag or (item.get('max_pct', 0) > 9.0 and pct < 9.0)
        if is_zb and pct > -7.0: tags.append("👀焚诀预期/炸板")

        return tags


class SidewaysChipStrategy(BaseStrategy):
    """
    【赫萝Horoo模式】核心票横盘二波博弈策略
    """

    def __init__(self, history_map: Dict, tushare_api=None):
        self.history_map = history_map
        self.pro = tushare_api
        self.cache = {}

    def run(self, item: Dict) -> List[str]:
        code = item['code']
        if code not in self.history_map: return []

        df = self.history_map[code]
        if len(df) < 35: return []

        # --- 技术面初筛 ---
        past_window = df.iloc[-35:-5]
        if len(past_window) < 10: return []

        range_high = past_window['high'].max()
        range_low = past_window['low'].min()
        range_pct = (range_high - range_low) / range_low
        has_limit_up = (past_window['pct_chg'] > 9.5).any()

        if not (range_pct > 0.25 or has_limit_up): return []

        recent_window = df.iloc[-5:]
        recent_high = recent_window['high'].max()
        recent_low = recent_window['low'].min()

        if (recent_high - recent_low) / recent_low > 0.15: return []
        if recent_window.iloc[-1]['close'] < range_high * 0.70: return []

        ma20 = df.iloc[-20:]['close'].mean()
        if recent_window.iloc[-1]['close'] < ma20 * 0.98: return []

        # --- 筹码面精选 ---
        base_tag = "👀横盘核心(结构好)"
        if not self.pro: return [base_tag]

        try:
            ts_code = self._format_ts_code(code)
            trade_date = df.iloc[-1]['trade_date']
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.strftime("%Y%m%d")

            cache_key = f"{code}_{trade_date}"
            if cache_key in self.cache:
                chip_data = self.cache[cache_key]
            else:
                df_cyq = self.pro.cyq_perf(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
                if df_cyq.empty: return [base_tag]
                chip_data = df_cyq.iloc[0]
                self.cache[cache_key] = chip_data

            winner_rate = chip_data['winner_rate']
            cost_95 = chip_data['cost_95pct']
            cost_5 = chip_data['cost_5pct']
            avg_cost = chip_data['weight_avg']
            concentration = (cost_95 - cost_5) / (avg_cost + 0.01)

            tags = []
            if winner_rate >= 80:
                tags.append(f"👑横盘筹码王(获利{int(winner_rate)}%)")
            elif winner_rate >= 50 and concentration < 0.20:
                tags.append(f"🚀横盘密集(获利{int(winner_rate)}%)")
            else:
                tags.append(base_tag)
            return tags

        except Exception as e:
            print(f"[ChipStrategy] Error: {e}")
            return [base_tag]

    def _format_ts_code(self, code):
        if code.startswith('6'): return f"{code}.SH"
        if code.startswith('0') or code.startswith('3'): return f"{code}.SZ"
        if code.startswith('8') or code.startswith('4'): return f"{code}.BJ"
        return f"{code}.SH"