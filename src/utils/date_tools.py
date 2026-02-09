# src/utils/date_tools.py

from datetime import datetime, timedelta
from colorama import Fore


class DateUtils:
    @staticmethod
    def get_smart_trading_date(tushare_client):
        """
        📅 智能交易日期获取 (去依赖版)
        优先使用本地逻辑判断工作日，仅用 Tushare 校验。
        """
        now = datetime.now()

        # 1. 初始基准: 下午4点前取昨天，4点后取当天
        if now.hour < 16:
            base_date = now - timedelta(days=1)
        else:
            base_date = now

        # 2. 📅 本地周末处理 (核心修复)
        # weekday(): 0=周一 ... 5=周六, 6=周日
        # 如果是周六(5)，退回周五(减1天)
        # 如果是周日(6)，退回周五(减2天)
        if base_date.weekday() == 5:
            print(f"{Fore.YELLOW}📅 检测到基准日是周六，自动回溯到周五...")
            base_date -= timedelta(days=1)
        elif base_date.weekday() == 6:
            print(f"{Fore.YELLOW}📅 检测到基准日是周日，自动回溯到周五...")
            base_date -= timedelta(days=2)

        base_date_str = base_date.strftime('%Y%m%d')
        print(f"{Fore.CYAN}🕒 [DateUtils] 智能锁定日期: {base_date_str} (周{base_date.weekday() + 1})")

        # 3. 尝试用 Tushare 校验 (仅作参考，失败也不怕)
        if tushare_client:
            try:
                # 查一下日历，以此判断是不是节假日(非周末的假期)
                # 往前多查几天，防止代理数据滞后导致查不到
                start_check = (base_date - timedelta(days=10)).strftime('%Y%m%d')
                df_cal = tushare_client.trade_cal(exchange='', start_date=start_check, end_date=base_date_str,
                                                  is_open='1')

                if not df_cal.empty:
                    last_open = df_cal.iloc[-1]['cal_date']
                    # 只有当接口返回的日期很新(7天内)且不等于我们算的日期时，才采纳接口
                    # 这样规避了代理日历滞后(30天前)的问题
                    last_open_dt = datetime.strptime(last_open, "%Y%m%d")
                    if (base_date - last_open_dt).days < 7 and last_open != base_date_str:
                        print(f"{Fore.YELLOW}📅 修正: 依据日历调整为 {last_open}")
                        return last_open
            except Exception:
                pass  # 接口挂了就忽略，用本地算的

        return base_date_str