from .base import BaseDataStep

class SmartMoneyStep(BaseDataStep):
    """[P5] 游资明细"""
    def fetch(self, date_str, context):
        print(f"   ├── [5/6] 获取游资明细...", end="", flush=True)
        try:
            df = self.pro.hm_detail(trade_date=date_str)
            context['hm_map'] = {}
            if not df.empty:
                for _, r in df.iterrows():
                    amt = float(r.get('net_amount', 0))
                    if abs(amt) < 5000000: continue
                    action = f"{r['hm_name']}{'买' if amt>0 else '卖'}{int(abs(amt)/10000)}w"
                    code = r['ts_code']
                    if code not in context['hm_map']: context['hm_map'][code] = []
                    context['hm_map'][code].append(action)
            print(f" ✅ ({len(df)}条)")
        except:
            context['hm_map'] = {}
            print(" ⚠️ 跳过")

    def enrich(self, stock, row, context):
        actions = context.get('hm_map', {}).get(stock.ts_code)
        if actions:
            for act in actions: stock.add_tag(f"🐉{act}")