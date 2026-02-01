# ==============================================================================
# 📈 技术面策略 (src/strategies/technical.py)
# 包含：均线趋势、断板反包、DDD模式、焚诀模型
# ==============================================================================

from typing import Dict, List
from .base import BaseStrategy
from src.data.market import TechnicalAnalyzer

# 尝试导入外部独立策略文件（如果你的项目结构里有的话）
# 如果没有，这些函数需要在外部定义或mock
try:
    from src.strategies.ddd_mode import get_ddd_pool_category
    from src.strategies.f_lao_model import check_fen_jue
except ImportError:
    # 兜底：如果没有这些文件，定义空函数防止报错
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

        # 必须要有历史数据才能计算
        if code not in self.history_map:
            return []

        # 调用 TechnicalAnalyzer 计算指标
        tags, _ = TechnicalAnalyzer.calculate_indicators(self.history_map[code], price)

        # 可以在这里做后处理，例如重命名标签
        final_tags = []
        for t in tags:
            if t == "🎯5日线低吸":
                final_tags.append("🎯5日线低吸(F佬推荐)")
            else:
                final_tags.append(t)

        # 焚诀模型 (依赖历史数据)
        f_tags = check_fen_jue(self.history_map[code])
        if f_tags:
            final_tags.extend(f_tags)

        return final_tags


class DDDStrategy(BaseStrategy):
    """
    DDD (大订单/特定模式) 策略
    """

    def run(self, item: Dict) -> List[str]:
        ddd_tag = get_ddd_pool_category(item)
        if ddd_tag:
            return [ddd_tag]
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

        # 1. 昨断板今反包
        if code in self.broken_pool_map and pct > 0:
            yest_amt = self.broken_pool_map[code]['amount']
            label = "🔥A大焚诀"  # 原代码逻辑替换了名称
            if yest_amt > 10000 and item.get('amount', 0) > yest_amt:
                label += "/爆量"
            tags.append(label)

        # 2. 跌停博弈
        if pct <= -9.0:
            tags.append("📉跌停/博弈修复")

        # 3. 炸板预期
        is_zb = "炸板" in raw_tag or (item.get('max_pct', 0) > 9.0 and pct < 9.0)
        if is_zb and pct > -7.0:
            tags.append("👀焚诀预期/炸板")

        return tags