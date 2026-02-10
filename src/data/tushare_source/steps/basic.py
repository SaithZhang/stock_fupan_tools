import pandas as pd
from .base import BaseDataStep


class BasicInfoStep(BaseDataStep):
    """[P1] 基础行情与昨收"""

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):        # 动态生成前缀
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[1/?]"
        print(f"   ├── {prefix} 获取基础行情...", end="", flush=True)

        df_daily = self.pro.daily(trade_date=date_str)
        df_basic = self.pro.daily_basic(trade_date=date_str,
                                        fields='ts_code,turnover_rate,circ_mv,total_mv,volume_ratio')

        # 获取昨日数据
        df_prev = pd.DataFrame()
        try:
            cal = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)
            dates = cal['cal_date'].tolist()
            if len(dates) == 2:
                df_prev = self.pro.daily(trade_date=dates[0], fields='ts_code,vol')
                df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
        except:
            pass

        df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')
        if not df_prev.empty:
            df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
        else:
            df_merge['last_vol'] = 0

        context['main_df'] = df_merge
        print(" ✅")