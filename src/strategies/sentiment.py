# ==============================================================================
# 🎭 情绪面策略集合 (src/strategies/sentiment.py)
# ==============================================================================
from typing import List, Union
from src.core.domain import Stock
from src.strategies.interface import Strategy


class IdentityStrategy(Strategy):
    """
    【玄学/名字策略】
    逻辑：检测名字中是否包含特定关键字（如：龙、中、华、科技等）。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        name = self.get_str(stock, 'name')
        labels = []

        keywords = ['龙', '凤', '中', '华', '国', 'AI']
        for kw in keywords:
            if kw in name:
                labels.append(f"🐉玄学:{kw}")

        return labels


class LHBStrategy(Strategy):
    """
    【龙虎榜策略】
    逻辑：检测是否有龙虎榜数据（需要 fetcher 提前注入 has_lhb 字段）。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        # 假设 fetcher 里如果上榜，会标记 is_lhb=True 或存入 lhb_info
        # 这里做个兼容判断
        is_lhb = getattr(stock, 'is_lhb', False) or self.get_str(stock, 'lhb_date') != ""

        if is_lhb:
            return ["🐯龙虎榜"]
        return []