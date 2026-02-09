# ==============================================================================
# 📈 技术面策略集合 (src/strategies/technical.py)
# ==============================================================================
from typing import List, Union
from src.core.domain import Stock
from src.strategies.interface import Strategy


class TrendStrategy(Strategy):
    """
    【趋势多头策略】
    逻辑：MA5 > MA10 > MA20，且当前价格在MA5之上，呈现完美的上升通道。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        ma5 = self.get_val(stock, 'ma5')
        ma10 = self.get_val(stock, 'ma10')
        ma20 = self.get_val(stock, 'ma20')
        price = self.get_val(stock, 'price')

        # 简单的多头排列判断
        if price > ma5 > ma10 > ma20 > 0:
            return ["📈趋势多头"]
        return []


class ReboundStrategy(Strategy):
    """
    【回踩支撑策略】
    逻辑：股价回踩 MA10 或 MA20 均线附近（最低价触及均线，但收盘价未有效跌破）。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        ma10 = self.get_val(stock, 'ma10')
        ma20 = self.get_val(stock, 'ma20')
        low = self.get_val(stock, 'low', 99999)  # 默认给个大数
        close = self.get_val(stock, 'price')

        labels = []
        if ma10 > 0 and low <= ma10 <= close:
            labels.append("🛡️回踩10日线")

        if ma20 > 0 and low <= ma20 <= close:
            labels.append("🛡️回踩20日线")

        return labels


class DDDStrategy(Strategy):
    """
    【大帝(DDD)放量策略】
    逻辑：关注放量滞涨或巨量突破。
    标准：量比 > 1.8 或 换手率 > 10%
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        vol_ratio = self.get_val(stock, 'vol_ratio')
        turnover = self.get_val(stock, 'turnover')

        labels = []
        if vol_ratio > 1.8:
            labels.append(f"🔥量比放大({vol_ratio:.1f})")

        if turnover > 10:
            labels.append(f"💰高换手({int(turnover)}%)")

        return labels


class SidewaysChipStrategy(Strategy):
    """
    【横盘震荡策略】
    逻辑：过去20天波动幅度很小，筹码在沉淀。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        # 注意：这里假设 stock 对象里有 20日最高/最低价 字段
        # 如果没有，需要 fetcher 里先计算好，或者在这里进行更复杂的判断
        high_20 = self.get_val(stock, 'high_20d')
        low_20 = self.get_val(stock, 'low_20d')

        if high_20 > 0 and low_20 > 0:
            amplitude = (high_20 - low_20) / low_20
            if amplitude < 0.15:  # 20天波动小于 15%
                return ["💤极度横盘"]

        return []