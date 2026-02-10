# ==============================================================================
# 🧠 竞价策略逻辑 (src/strategies/auction.py)
# Version: 3.5 (Unified Interface)
# ==============================================================================

import re
from colorama import Fore, Style


class AuctionStrategy:

    def analyze(self, auc_pct, ratio, ctx):
        """
        [标准接口] 供 Screener 和 Backtest 统一调用
        :param auc_pct: 竞价涨幅
        :param ratio: 量比 (竞价额/昨成交额)
        :param ctx: 上下文 {'yest_pct': float, 'is_broken': bool, 'yest_tag': str}
        :return: (decision_str, color_code)
        """
        yest_pct = ctx.get('yest_pct', 0)
        yest_tag = str(ctx.get('yest_tag', ''))
        is_broken = ctx.get('is_broken', False)  # 外部传入是否炸板

        # 1. 弱转强判定 (核心)
        # 定义“弱”: 昨跌 OR 炸板 OR 断板
        is_weak = (yest_pct < 0) or is_broken or ("炸板" in yest_tag) or ("断板" in yest_tag)

        decision = ""
        color = ""

        if is_weak and auc_pct > 0.0:  # 弱转强基础: 昨弱今红
            if auc_pct > 5.0:
                decision = "🔥弱转强[高开]"
                color = Fore.RED
            elif ratio > 5.0:  # 竞价量比 > 5% (爆量)
                decision = "🔥弱转强[爆量]"
                color = Fore.MAGENTA
            else:
                decision = "🔥弱转强"  # 普通
                color = Fore.RED

        # 2. 核按钮/核反转判定
        elif auc_pct < -4.0:
            decision = "📉核按钮"
            color = Fore.GREEN
            # 如果是某些特定模式（如高标断板后的核按钮），可能是“核反转”的买点，这里暂只标记状态

        # 3. 抢筹判定
        elif ratio > 10.0 and auc_pct > 0:
            decision = "💰抢筹"
            color = Fore.YELLOW

        else:
            decision = "👀观察"
            color = Fore.WHITE

        return decision, color

    @staticmethod
    def analyze_status(yest_pct, auc_pct, yest_tag, code_in_holdings):
        """(兼容旧代码的辅助方法)"""
        status_flags = []

        # 弱转强逻辑复用
        is_weak_yest = (yest_pct < 0) or ("炸板" in yest_tag) or ("断板" in yest_tag)
        if is_weak_yest and auc_pct > 0.5:
            status_flags.append(f"{Fore.RED}🔥弱转强{Style.RESET_ALL}")

        if auc_pct < -4.0:
            status_flags.append(f"{Fore.GREEN}📉核按钮{Style.RESET_ALL}")
        elif auc_pct > 4.0:
            status_flags.append(f"{Fore.RED}★高开{Style.RESET_ALL}")

        if code_in_holdings:
            status_flags.insert(0, f"{Fore.MAGENTA}[持]{Style.RESET_ALL}")

        return " ".join(status_flags)

    @staticmethod
    def clean_tag(tag, board_cnt):
        """清洗冗余标签"""
        if board_cnt > 0:
            tag = tag.replace(f"{board_cnt}板", "").replace(f"{board_cnt}进{board_cnt + 1}", "")
        redundant = ["DDD", "1进2", "2进3", "3进4", "高开", "/", "nan"]
        for w in redundant:
            tag = tag.replace(w, "")
        tag = tag.replace("A大焚诀", "A大").replace("龙虎榜", "LHB").replace("F佬/1.26复盘", "F佬").replace("复盘", "")
        tag = re.sub(r'/+', '/', tag).strip('/')
        return tag[:22]