# ==============================================================================
# 🧠 竞价策略逻辑 (src/strategies/auction.py)
# 包含：弱转强判定、核按钮识别、标签清洗
# ==============================================================================

import re
from colorama import Fore, Style


class AuctionStrategy:
    @staticmethod
    def analyze_status(yest_pct, auc_pct, yest_tag, code_in_holdings):
        """
        综合判定竞价状态
        :return: (StatusString, IsHighlight)
        """
        status_flags = []

        # 1. 弱转强 (昨绿/炸板 -> 今红)
        is_weak_yest = (yest_pct < 0) or ("炸板" in yest_tag) or ("断板" in yest_tag)
        if is_weak_yest and auc_pct > 0.5:
            status_flags.append(f"{Fore.RED}🔥弱转强{Style.RESET_ALL}")

        # 2. 极端开盘
        if auc_pct < -4.0:
            status_flags.append(f"{Fore.GREEN}📉核按钮{Style.RESET_ALL}")
        elif auc_pct > 4.0:
            status_flags.append(f"{Fore.RED}★高开{Style.RESET_ALL}")

        # 3. 持仓标记
        if code_in_holdings:
            status_flags.insert(0, f"{Fore.MAGENTA}[持]{Style.RESET_ALL}")

        return " ".join(status_flags)

    @staticmethod
    def check_volume(yest_amt, auc_amt):
        """爆量检测"""
        is_huge = False
        # 昨额非0且竞价占比>10%，或者绝对金额>5000万
        if yest_amt > 0 and auc_amt > yest_amt * 0.1:
            is_huge = True
        if auc_amt > 5000_0000:
            is_huge = True
        return is_huge

    @staticmethod
    def clean_tag(tag, board_cnt):
        """清洗冗余标签，提取核心逻辑"""
        # 移除板数
        if board_cnt > 0:
            tag = tag.replace(f"{board_cnt}板", "").replace(f"{board_cnt}进{board_cnt + 1}", "")

        # 移除无用词
        redundant = ["DDD", "1进2", "2进3", "3进4", "高开", "/", "nan"]
        for w in redundant:
            tag = tag.replace(w, "")

        # 简化长词
        tag = tag.replace("A大焚诀", "A大").replace("龙虎榜", "LHB")
        tag = tag.replace("F佬/1.26复盘", "F佬").replace("复盘", "")

        # 修复格式
        tag = re.sub(r'/+', '/', tag).strip('/')
        return tag[:22]

    @staticmethod
    def get_board_count(tag):
        match = re.search(r'(\d+)板', tag)
        return int(match.group(1)) if match else 0