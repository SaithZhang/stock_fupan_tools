from colorama import Fore, Back, Style
from typing import Dict, List
from .models import LiveStockContext
from .strategies import (
    BaseFilter, BaseStrategy, STFilter, MinAuctionAmountFilter,
    OneLineBoardStrategy, DistributionTrapStrategy, OldDragonBreakoutStrategy,
    WeakToStrongStrategy, MainForceResonanceStrategy, TrendDipStrategy, HighOpenRiskStrategy
)


class AuctionScreenerEngine:
    def __init__(self):
        # 1. 注册拦截器 (责任链：一旦未通过，直接出局)
        self.filters: List[BaseFilter] = [
            STFilter(),
            MinAuctionAmountFilter()
        ]

        # 2. 注册战法策略 (严格按优先级先后排序！一旦匹配立刻终止流转)
        self.strategies: List[BaseStrategy] = [
            OneLineBoardStrategy(),
            DistributionTrapStrategy(),  # 拦截陷阱优先级极高
            OldDragonBreakoutStrategy(),  # 核心战法
            WeakToStrongStrategy(),  # 核心战法
            MainForceResonanceStrategy(),
            TrendDipStrategy(),
            HighOpenRiskStrategy()
        ]

    def evaluate(self, ctx: LiveStockContext) -> Dict:
        """执行单只股票的流水分发"""
        # 第一阶段：黑名单拦截
        for f in self.filters:
            passed, reason = f.check(ctx)
            if not passed:
                return {'fail_reason': reason}

        # 第二阶段：策略引擎打分
        best_score = 60
        decision = "观察"

        for strategy in self.strategies:
            matched, score, desc = strategy.evaluate(ctx)
            if matched:
                best_score = score
                decision = desc
                break  # 命中高优先级策略，终止后续打分

        # 第三阶段：上下文加分项 (独立于战法，如持仓必顶)
        if ctx.pool_tag: best_score += 10
        if ctx.is_focus: best_score += 15
        if ctx.is_holding: best_score = 100

        if ctx.pool_tag:
            decision += f" {Back.MAGENTA}{Fore.WHITE}[{ctx.pool_tag}]{Style.RESET_ALL}"

        # 返回清洗后的扁平化结果给 UI 层
        return {
            'code': ctx.code, 'name': ctx.name, 'score': best_score, 'decision': decision,
            'open_pct': ctx.open_pct, 'real_pct': ctx.real_pct, 'auc': ctx.auc_amt,
            'yest_pct': ctx.yest_pct, 'boards': ctx.boards, 'circ_mv': ctx.circ_mv,
            'tag': ctx.pool_tag, 'sector_info': ctx.industry, 'last_amt': ctx.last_amt,
            'is_holding': ctx.is_holding, 'is_focus': ctx.is_focus
        }