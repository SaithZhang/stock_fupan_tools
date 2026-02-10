from .base import BaseDataStep

class SentimentStep(BaseDataStep):
    """[P4] 市场热度"""
    def fetch(self, date_str, context):
        print(f"   ├── [4/6] 获取市场热度...", end="", flush=True)
        try:
            df_hot = self.pro.ths_hot(trade_date=date_str, market='热股', limit=200)
            context['hot_map'] = {}
            if not df_hot.empty:
                for _, r in df_hot.iterrows():
                    context['hot_map'][r['ts_code']] = int(r['rank'])
            print(f" ✅ (Top{len(context['hot_map'])})")
        except:
            context['hot_map'] = {}
            print(" ⚠️ 跳过")

    def enrich(self, stock, row, context):
        rank = context.get('hot_map', {}).get(stock.ts_code)
        if rank:
            if not hasattr(stock, 'tags'): stock.tags = []
            stock.add_tag(f"🔥Top{rank}")