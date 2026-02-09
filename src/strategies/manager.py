# ==============================================================================
# 🛡️ 策略管理器 (src/strategies/manager.py)
# ==============================================================================
from typing import List
from src.core.domain import Stock

# 导入具体策略 (注意：这里假设你的旧策略文件还在原位)
from src.strategies.base import BaseStrategy
from src.strategies.sentiment import IdentityStrategy, LHBStrategy
from src.strategies.technical import TrendStrategy, ReboundStrategy, DDDStrategy, SidewaysChipStrategy


class StrategyManager:
    def __init__(self):
        self.strategies: List[BaseStrategy] = []

    def load_strategies(self, context: dict):
        """
        统一装配策略
        """
        self.strategies = []

        # 1. 身份/持仓策略
        self.strategies.append(
            IdentityStrategy(context.get('holdings', {}), context.get('f_lao', {}), context.get('manual', {}))
        )

        # 2. 龙虎榜策略
        if 'lhb_codes' in context:
            self.strategies.append(LHBStrategy(context['lhb_codes'], context.get('seat_map', {})))

        # 3. 趋势策略 (依赖历史K线)
        if 'history' in context:
            self.strategies.append(TrendStrategy(context['history']))
            self.strategies.append(SidewaysChipStrategy(context['history'], None))  # Pro暂传None

        # 4. 情绪/反核策略
        self.strategies.append(ReboundStrategy(context.get('broken_pool', {})))

        # 5. 形态策略
        self.strategies.append(DDDStrategy())

        print(f"🛡️ 已加载 {len(self.strategies)} 个作战策略")

    def execute_all(self, stock: Stock) -> List[str]:
        """
        对一只股票执行所有策略
        """
        hit_tags = []
        for strategy in self.strategies:
            try:
                # 兼容性调用：旧策略的 run 方法可能需要 dict，
                # 但我们的 Stock 对象实现了 __getitem__，所以可以直接传！
                tags = strategy.run(stock)
                if tags:
                    if isinstance(tags, list):
                        hit_tags.extend(tags)
                    elif isinstance(tags, str):
                        hit_tags.append(tags)
            except Exception as e:
                # 生产环境建议 log error，不要 print 刷屏
                pass

        # 去重
        return list(set(hit_tags))