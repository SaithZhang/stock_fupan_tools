# ==============================================================================
# 🏭 策略工厂 V3.4 (src/core/pool_generator_tushare.py)
# Version: 3.4 (Aggressive Active Filter - Target 300)
# Fix: 适配 V4.0 Modular Fetcher 架构
# ==============================================================================

import os
import sys
from colorama import init, Fore
from typing import List

init(autoreset=True)

# 路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
    from src.data.market import MarketAnalyzer
    from src.data.loader import SystemDataLoader

    from src.data.tushare_source.client import TushareClient
    from src.data.tushare_source.fetcher import TushareFetcher
    from src.data.market_data import MarketDataManager

    from src.core.domain import Stock
    from src.strategies.manager import StrategyManager

    from src.core.stock_tagger import StockTagger
    from src.data.exporter import ResultExporter
    from src.utils.date_tools import DateUtils
    from src.strategies.f_lao_model import load_ths_history
    # ✅ 新增：引入过滤器
    from src.core.filter import StockFilter

except ImportError as e:
    print(f"{Fore.RED}❌ 关键模块缺失: {e}")
    sys.exit(1)


class PoolGeneratorV3:
    def __init__(self):
        self.pro = TushareClient.get_pro()
        self.fetcher = TushareFetcher()
        self.md_manager = MarketDataManager()
        self.strategy_manager = StrategyManager()
        # ✅ 初始化过滤器
        self.filter = StockFilter()

        self.all_data: List[Stock] = []
        self.context = {
            'holdings': {}, 'f_lao': {}, 'manual': {}, 'broken_pool': {},
            'lhb_codes': set(), 'seat_map': {}, 'history': {}
        }
        self.top_amount_threshold = 0
        self.risk_map = {}

    def load_resources(self) -> bool:
        print(f"{Fore.CYAN}📥 [1/4] Tushare Pro 资源加载...")

        target_date = DateUtils.get_smart_trading_date(self.pro)
        print(f"   📅 锁定复盘日期: {Fore.YELLOW}{target_date}{Fore.RESET}")

        # 1. 指数 (调用 market 组件)
        # Fix: 使用 V4.0 market 组件
        index_data = self.fetcher.market.fetch_index(target_date)
        self.md_manager.update_indices(index_data)

        # 2. 全市场数据 (调用 stocks 流水线)
        # Fix: 使用 V4.0 stocks 引擎
        self.all_data = self.fetcher.stocks.run(target_date)

        if not self.all_data:
            print(f"{Fore.RED}❌ 数据拉取失败")
            return False

        # 3. 同花顺概览 (调用 market 组件)
        # Fix: 使用 V4.0 market 组件
        ths_stats = self.fetcher.market.fetch_limit_stats(target_date)
        self.md_manager.update_stats(ths_stats)

        # 4. Top50 门槛
        if self.all_data:
            amounts = sorted([s.amount for s in self.all_data], reverse=True)
            if len(amounts) > 50:
                self.top_amount_threshold = amounts[50]
                print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 5. 上下文
        self.context['holdings'] = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.context['f_lao'] = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.context['manual'] = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.context['broken_pool'] = SystemDataLoader.load_yesterday_pool()
        self.risk_map = SystemDataLoader.load_risk_data()

        try:
            df_lhb = self.pro.top_list(trade_date=target_date)
            if not df_lhb.empty:
                self.context['lhb_codes'] = set(df_lhb['ts_code'].apply(lambda x: x.split('.')[0]).tolist())
        except:
            pass

        _, local_seat_map = SystemDataLoader.load_lhb_info()
        self.context['seat_map'] = local_seat_map
        self.context['history'] = load_ths_history(Config.THS_DIR, days=30)

        return True

    def run_pipeline(self):
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V3.4 Aggressive Filter)...")

        # 1. 批量运行策略
        df_res = self.strategy_manager.run_all(self.all_data)

        tag_map = {}
        if not df_res.empty and 'tag' in df_res.columns:
            tag_map = df_res.set_index('ts_code')['tag'].to_dict()

        tagger = StockTagger(self.top_amount_threshold)
        results_pool = []

        filtered_count = 0

        # 2. 遍历并过滤
        for stock in self.all_data:
            if stock.is_st:
                continue

            tag_str = tag_map.get(stock.ts_code, "")
            hit_tags = tag_str.split(" | ") if tag_str else []

            # 传入 context 供过滤器使用
            if not self.filter.check(stock, hit_tags, self.context):
                continue

            final_tag_str, is_selected, zt_type = tagger.get_tags(stock, hit_tags)

            if is_selected:
                stock.limit_type = zt_type
                stock.add_tag(final_tag_str)
                stock.tags = [final_tag_str]

                item_dict = stock.to_dict()
                item_dict['link_dragon'] = TextUtils.get_link_dragon(stock.code)

                risk_info = self.risk_map.get(stock.name, {'risk_level': '🟢 Safe'})
                item_dict.update(risk_info)

                results_pool.append(item_dict)
            else:
                filtered_count += 1

        print(f"   🧹 已过滤弱势/非活跃标的: {len(self.all_data) - len(results_pool)} 只")
        print(f"   💎 最终入池: {len(results_pool)} 只")

        # 🔥 Fix: 修复此处的旧调用，使用新架构
        ths_stats = self.fetcher.market.fetch_limit_stats(DateUtils.get_smart_trading_date(self.pro))

        phase_info = MarketAnalyzer.analyze_phase(results_pool, ths_stats)
        self.md_manager.update_stats(phase_info)

        print(f"\n{Fore.YELLOW}{self.md_manager.get_formatted_summary()}")
        ResultExporter.export_pool(results_pool)


if __name__ == "__main__":
    generator = PoolGeneratorV3()
    generator.run_pipeline()