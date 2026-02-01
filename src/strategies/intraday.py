# ==============================================================================
# ⚡ 盘中策略 (src/strategies/intraday.py)
# 职责：涨跌停判断、分时异动监测、颜色管理
# ==============================================================================

from colorama import Fore, Style


class IntradayStrategy:
    @staticmethod
    def check_status(price, limit_up, limit_down, pct):
        """判断当前股票状态 (涨停/跌停/普通)"""
        # 涨停 (考虑精度误差)
        if price >= limit_up - 0.01:
            # 区分一字板逻辑需结合开盘价，这里简化为只看当前是否封板
            return f"{Fore.MAGENTA}🔥涨停{Style.RESET_ALL}", True
        # 跌停
        elif price <= limit_down + 0.01:
            return f"{Fore.GREEN}📉跌停{Style.RESET_ALL}", False

        return "", False

    @staticmethod
    def check_dynamic_alert(curr_price, last_price):
        """
        分时异动检测
        :return: 异动信号字符串 or ""
        """
        if last_price <= 0 or curr_price <= 0: return ""

        # 计算瞬间涨幅 (Tick级别)
        delta_pct = (curr_price - last_price) / last_price * 100

        if delta_pct > 1.2:
            return f"{Fore.RED}🚀急拉{Style.RESET_ALL}"
        elif delta_pct > 0.8:
            return f"{Fore.RED}⚡异动{Style.RESET_ALL}"
        elif delta_pct < -1.2:
            return f"{Fore.GREEN}🌊跳水{Style.RESET_ALL}"

        return ""

    @staticmethod
    def get_pct_color(pct):
        if pct > 9.5: return Fore.MAGENTA
        if pct > 0: return Fore.RED
        if pct < -9.5: return Fore.BLUE  # 跌停深蓝/绿
        if pct < 0: return Fore.GREEN
        return Fore.WHITE