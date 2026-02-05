# src/utils/date_tools.py

from datetime import datetime, timedelta
from colorama import Fore


class DateUtils:
    @staticmethod
    def get_smart_trading_date(tushare_client):
        """
        📅 智能交易日期获取 (静态工具方法)

        Args:
            tushare_client: Tushare Pro 接口客户端 (pro = ts.pro_api())

        Returns:
            str: 格式化的日期字符串 'YYYYMMDD'
        """
        now = datetime.now()

        # 1. 判定基准日期: 下午4点前取昨天，4点后取当天
        if now.hour < 16:
            base_date = now - timedelta(days=1)
        else:
            base_date = now

        base_date_str = base_date.strftime('%Y%m%d')
        # 往前查 30 天，确保覆盖长假
        start_date_str = (base_date - timedelta(days=30)).strftime('%Y%m%d')

        print(f"{Fore.CYAN}🕒 [DateUtils] 系统时间: {now.strftime('%H:%M')} | 基准检测日期: {base_date_str}")

        if not tushare_client:
            print(f"{Fore.RED}⚠️ Tushare 客户端未初始化，强制使用基准日期")
            return base_date_str

        try:
            # 2. 查询交易日历
            # is_open='1' 代表开盘
            df_cal = tushare_client.trade_cal(exchange='', start_date=start_date_str, end_date=base_date_str,
                                              is_open='1')

            if not df_cal.empty:
                target_date = df_cal.iloc[-1]['cal_date']  # 取日历中最后一个交易日

                # 3. 🛡️ 数据新鲜度防御检查
                # 防止因为 Tushare 接口或本地数据未更新，导致回退到很久以前的日期
                target_dt = datetime.strptime(target_date, "%Y%m%d")
                days_diff = (base_date - target_dt).days

                if days_diff > 7:
                    print(f"{Fore.YELLOW}⚠️ 警告: 接口返回的最新交易日 ({target_date}) 距今已 {days_diff} 天。")
                    print(f"{Fore.YELLOW}👉 可能原因: Tushare/代理数据未更新。")
                    print(f"{Fore.GREEN}🛡️ 启动防御措施: 强制使用基准日期 {base_date_str}")
                    return base_date_str

                return target_date
            else:
                print(f"{Fore.RED}⚠️ 未找到交易日历数据，强制使用基准日期")
                return base_date_str

        except Exception as e:
            print(f"{Fore.RED}⚠️ 日历接口请求失败，降级使用基准日期: {e}")
            return base_date_str