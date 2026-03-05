import pandas as pd
from colorama import Fore
from .base import BaseDataStep

class BasicInfoStep(BaseDataStep):
    """[P1] 基础行情与昨收"""

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[1/?]"
        print(f"   ├── {prefix} 获取基础行情...", end="", flush=True)

        # 1. 获取当日数据 (改用 start_date 和 end_date 组合)
        df_daily = self.pro.daily(start_date=date_str, end_date=date_str)
        df_basic = self.pro.daily_basic(start_date=date_str, end_date=date_str,
                                        fields='ts_code,turnover_rate,circ_mv,total_mv,volume_ratio')

        # 👇 严格的数据非空校验
        if df_daily is None or df_daily.empty:
            print(f" {Fore.RED}❌ 失败 (Tushare 返回 {date_str} daily 数据为空){Fore.RESET}")
            context['main_df'] = pd.DataFrame()
            return

        if df_basic is None or df_basic.empty:
            print(f" {Fore.YELLOW}⚠️ 警告 (未获取到 {date_str} daily_basic 数据){Fore.RESET}")

        # 2. 获取昨日数据 (用于对比计算)
        df_prev = pd.DataFrame()
        try:
            # trade_cal 接口通常只支持 end_date 和 limit，这个保持不变
            cal = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)
            dates = cal['cal_date'].tolist()
            if len(dates) == 2:
                # dates[0] 是上一个交易日，dates[1] 是当前交易日 date_str
                # 改用 start_date 和 end_date 获取昨日行情
                df_prev = self.pro.daily(start_date=dates[0], end_date=dates[0], fields='ts_code,vol')
                df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
        except Exception as e:
            # 静默处理，后面兜底为 0
            pass

        # 3. 数据合并
        df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')
        if not df_prev.empty:
            df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
        else:
            df_merge['last_vol'] = 0

        # 4. 写入上下文
        context['main_df'] = df_merge

        # 打印出实际获取到的数据条数，对齐其他步骤的日志格式
        print(f" ✅ ({len(df_merge)}条)")