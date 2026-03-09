from colorama import Fore, Style
from typing import Tuple
from .models import LiveStockContext

# ==============================================================================
# 🤖 AI 开发者与策略扩展指南 (How to add a new strategy):
#
# 1. 拦截器扩展：继承 `BaseFilter`，实现 `check(ctx)`。返回 (False, "理由") 即秒杀淘汰。
# 2. 战法策略扩展：继承 `BaseStrategy`，实现 `evaluate(ctx)`。
#    - 若命中战法：返回 `True, 分数(0-100), "带颜色的决策文案"`
#    - 若未命中：返回 `False, 0, ""`
# 3. 注册：写完新类后，务必去 `engine.py` 的列表中注册，且注意**列表顺序即优先级**！
# ==============================================================================

class BaseFilter:
    def check(self, ctx: LiveStockContext) -> Tuple[bool, str]:
        raise NotImplementedError

class BaseStrategy:
    def evaluate(self, ctx: LiveStockContext) -> Tuple[bool, int, str]:
        raise NotImplementedError

# ------------------------------------------------------------------------------
# 🛡️ 拦截器区 (Filters)
# ------------------------------------------------------------------------------
class STFilter(BaseFilter):
    def check(self, ctx: LiveStockContext):
        if 'ST' in ctx.name.upper() and not ctx.is_holding:
            return False, '过滤ST股'
        return True, ""

class MinAuctionAmountFilter(BaseFilter):
    def check(self, ctx: LiveStockContext):
        min_auc = 1000  # 普通股门槛
        if ctx.pool_tag: min_auc = 500  # 底库股放宽
        if ctx.is_focus: min_auc = 300  # 关注股放宽
        if ctx.is_holding: min_auc = 0  # 持仓无视门槛

        if ctx.auc_amt < min_auc:
            return False, f'竞价弱势({ctx.auc_amt:.0f}万<{min_auc}万)'
        return True, ""

# ------------------------------------------------------------------------------
# ⚔️ 战法策略区 (Strategies)
# ------------------------------------------------------------------------------
class OneLineBoardStrategy(BaseStrategy):
    """一字板加速过滤"""
    def evaluate(self, ctx):
        if ctx.open_pct > 9.8:
            score = 80 if ctx.is_focus else 0  # 买不到的不看，除非特别关注
            return True, score, f"{Fore.BLUE}🔒 一字板加速{Style.RESET_ALL}"
        return False, 0, ""


class DistributionTrapStrategy(BaseStrategy):
    """💣 防雷：巨量滞涨派发陷阱"""

    def evaluate(self, ctx):
        if ctx.auc_amt >= 5000 and -3.0 <= ctx.open_pct < 3.0 and ctx.last_amt >= 10000:
            # ✅ 新增免死金牌：如果它同板块有小弟涨停（有板块共振），或者是老龙，说明这是爆量承接，不是陷阱！
            if ctx.has_limit_up_brother or "[老龙横盘]" in ctx.pool_tag or "★人气/容量" in ctx.pool_tag:
                return False, 0, ""  # 豁免，交由后面的弱转强或主力共振去打高分

            return True, 30, f"{Fore.RED}💣 巨量滞涨(派发大坑/快跑){Style.RESET_ALL}"
        return False, 0, ""

class OldDragonBreakoutStrategy(BaseStrategy):
    """🐉 L大核心：老龙反推破局"""
    def evaluate(self, ctx):
        if "[老龙横盘]" in ctx.pool_tag and ctx.has_limit_up_brother:
            if ctx.open_pct >= 0.0 and ctx.auc_amt > 1000:
                return True, 98, f"{Fore.RED}🐉 老龙反推(小弟一字助攻){Style.RESET_ALL}"
        return False, 0, ""

class WeakToStrongStrategy(BaseStrategy):
    """🚀 核心：弱转强抢筹"""
    def evaluate(self, ctx):
        if ctx.yest_pct < 4.0 and ctx.open_pct > 1.5 and ctx.auc_amt > 1500:
            return True, 95, f"{Fore.MAGENTA}🚀 弱转强抢筹{Style.RESET_ALL}"
        if ("烂板" in ctx.pool_tag or "分歧" in ctx.pool_tag) and ctx.open_pct > 0.0 and ctx.auc_amt > 1000:
            return True, 95, f"{Fore.MAGENTA}🚀 弱转强(分歧转一致){Style.RESET_ALL}"
        return False, 0, ""

class MainForceResonanceStrategy(BaseStrategy):
    """🔥 主力抢筹共振"""
    def evaluate(self, ctx):
        if ("主力" in ctx.pool_tag or "抢筹" in ctx.pool_tag) and 0 < ctx.open_pct < 5.0:
            return True, 90, f"{Fore.RED}🔥 主力共振{Style.RESET_ALL}"
        return False, 0, ""

class TrendDipStrategy(BaseStrategy):
    """✅ 趋势深水回踩"""
    def evaluate(self, ctx):
        if ctx.open_pct <= -5.0 and ("低吸" in ctx.pool_tag or "趋势" in ctx.pool_tag):
            return True, 85, f"{Fore.GREEN}✅ 趋势深水回踩{Style.RESET_ALL}"
        return False, 0, ""

class HighOpenRiskStrategy(BaseStrategy):
    """⚠️ 高开缩量提示"""
    def evaluate(self, ctx):
        if 5.0 < ctx.open_pct < 9.8:
            return True, 60, f"{Fore.YELLOW}⚠️ 高开缩量风险{Style.RESET_ALL}"
        return False, 0, ""