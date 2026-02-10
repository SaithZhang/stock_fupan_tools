from .base import BaseDataStep
from colorama import Fore


class SentimentStep(BaseDataStep):
    """[P4] 市场热度 (同花顺/东方财富)"""

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[4/?]"
        print(f"   ├── {prefix} 获取市场热度...", end="", flush=True)
        hot_map = {}

        try:
            # 策略 A: 同花顺热榜 (ths_hot)
            # 关键修正: is_new='N' (获取盘中/盘后实时数据，不用等22:30)
            # 注意: 此接口需 6000 积分
            df_hot = self.pro.ths_hot(trade_date=date_str, market='热股', is_new='N')

            # 如果 'N' 没数据(比如复盘历史日期), 尝试 'Y' (历史最终榜)
            if df_hot.empty:
                df_hot = self.pro.ths_hot(trade_date=date_str, market='热股', is_new='Y')

            if not df_hot.empty:
                # 清洗数据: 按 rank 排序，取前 200
                if 'rank' in df_hot.columns:
                    df_hot['rank'] = df_hot['rank'].astype(int)
                    df_hot = df_hot.sort_values('rank').head(200)

                for _, r in df_hot.iterrows():
                    hot_map[r['ts_code']] = int(r['rank'])

                print(f" ✅ (同花顺 Top{len(hot_map)})")

            else:
                # 策略 B: 东方财富热榜 (dc_hot) - 作为备用，通常积分门槛低
                # print(f" (切换备用)...", end="")
                # df_dc = self.pro.dc_hot(trade_date=date_str, is_new='N') # 视您的权限开启
                # ...
                print(f" ⚠️ 无数据 (可能时间未到22:30或积分不足)")

        except Exception as e:
            print(f" ⚠️ 跳过: {e}")

        context['hot_map'] = hot_map

    def enrich(self, stock, row, context):
        rank = context.get('hot_map', {}).get(stock.ts_code)
        if rank:
            # 注入标签: 🔥Top1, 🔥Top5 ...
            if not hasattr(stock, 'tags'): stock.tags = []
            stock.add_tag(f"🔥Top{rank}")