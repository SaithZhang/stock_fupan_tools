from .base import BaseDataStep

class ChipStep(BaseDataStep):
    """[P6] 筹码分布"""
    def fetch(self, date_str, context):
        print(f"   ├── [6/6] 获取筹码分布...", end="", flush=True)
        try:
            df = self.pro.cyq_perf(trade_date=date_str)
            context['chip_map'] = df.set_index('ts_code').to_dict('index') if not df.empty else {}
            print(f" ✅")
        except:
            context['chip_map'] = {}
            print(" ⚠️ (暂无)")

    def enrich(self, stock, row, context):
        chip = context.get('chip_map', {}).get(stock.ts_code)
        if chip:
            stock.winner_rate = float(chip.get('winner_rate', 0))
            stock.cost_5pct = float(chip.get('cost_5pct', 0))
            stock.cost_95pct = float(chip.get('cost_95pct', 0))
            stock.weight_avg = float(chip.get('weight_avg', 0))