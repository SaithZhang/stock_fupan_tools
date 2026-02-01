# ==============================================================================
# 🧠 情绪与身份策略 (src/strategies/sentiment.py)
# 包含：持仓监控、F佬作业跟随、龙虎榜席位分析、人工重点关注
# ==============================================================================

from typing import Dict, List, Set
from .base import BaseStrategy

# 引入工具
try:
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
except ImportError:
    pass  # 忽略IDE报错，运行时路径通常正常


class IdentityStrategy(BaseStrategy):
    """
    身份识别策略：负责标记 持仓股、F佬作业、人工关注股
    """

    def __init__(self, holdings_map: Dict, f_lao_map: Dict, manual_map: Dict):
        self.holdings_map = holdings_map
        self.f_lao_map = f_lao_map
        self.manual_map = manual_map

    def run(self, item: Dict) -> List[str]:
        tags = []
        code = item['code']
        name = item['name']
        is_zt = item.get('is_zt', False)

        # 1. 优先处理 Config 中的特殊配置
        if code in Config.HOLDING_STRATEGIES:
            tags.append(Config.HOLDING_STRATEGIES[code][0])
            return tags  # 特殊配置通常覆盖其他

        # 2. 持仓标记
        if code in self.holdings_map:
            tags.append(f"持仓/{name}")

        # 3. F佬作业标记
        elif code in self.f_lao_map:
            raw_note = self.f_lao_map[code]
            # 调用工具类清洗标签
            cleaned_note = TextUtils.clean_manual_tag(raw_note, is_zt)
            final_manual = f"F佬/{cleaned_note}" if cleaned_note != "关注" else "F佬/关注"
            tags.append(final_manual)

        # 4. 人工关注/人气股
        # (原逻辑：limit_days>=3 或 成交额>20亿 或 在manual_map中)
        is_popular = False
        pop_reasons = []

        if code in self.manual_map or name in self.manual_map:
            is_popular = True

        if item.get('limit_days', 0) >= 3:
            is_popular = True

        if item.get('amount', 0) >= 20_0000_0000:  # 20亿
            is_popular = True
            pop_reasons.append("成交")

        if is_popular:
            tags.append("★人气")
            if pop_reasons: tags.extend(pop_reasons)

        return tags


class LHBStrategy(BaseStrategy):
    """
    龙虎榜策略：负责标记上榜个股及知名游资动作
    """

    def __init__(self, lhb_codes: Set[str], seat_map: Dict[str, Set[str]]):
        self.lhb_codes = lhb_codes
        self.seat_map = seat_map

    def run(self, item: Dict) -> List[str]:
        tags = []
        code = item['code']
        name = item['name']

        if code in self.lhb_codes:
            tags.append("🐉龙虎榜")

        if name in self.seat_map:
            # 排序逻辑：锁仓/加仓 -> 买入 -> 卖出 -> 其他
            def tag_sort(t):
                if t.startswith(("🔒", "➕")): return 0
                if t.startswith("💰"): return 1
                if t.startswith("🏃"): return 2
                return 3

            seats = sorted(list(self.seat_map[name]), key=tag_sort)
            tags.extend(seats)

        return tags