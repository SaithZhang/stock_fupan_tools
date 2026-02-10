import re
from .base import BaseDataStep


class LimitBoardStep(BaseDataStep):
    """[P3] 涨跌停"""

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[3/?]"
        print(f"   ├── {prefix} 获取涨跌停数据...", end="", flush=True)
        try:
            df_zt = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池',
                                            fields='ts_code,tag,status,lu_desc')
            context['zt_map'] = df_zt.set_index('ts_code').to_dict('index') if not df_zt.empty else {}
            context['zt_codes'] = set(df_zt['ts_code']) if not df_zt.empty else set()
            print(f" ✅ (涨停{len(df_zt)}家)")
        except:
            context['zt_map'] = {}
            print(" ❌")

    def enrich(self, stock, row, context):
        zt_info = context.get('zt_map', {}).get(stock.ts_code)
        if zt_info:
            stock.is_zt = True
            stock.ths_status = str(zt_info.get('tag', ''))
            stock.limit_type = str(zt_info.get('status', ''))
            stock.ths_desc = str(zt_info.get('lu_desc', ''))

            m = re.search(r'(\d+)(连板|板)', stock.ths_status)
            if m:
                stock.limit_days = int(m.group(1))
            elif '首板' in stock.ths_status:
                stock.limit_days = 1