# ==============================================================================
# 🏭 策略工厂 V3.1 (src/core/pool_generator_tushare.py)
# Version: 3.1 (Domain Driven Architecture)
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

    # ✨ 核心架构升级
    from src.core.domain import Stock
    from src.strategies.manager import StrategyManager

    from src.core.stock_tagger import StockTagger
    from src.data.exporter import ResultExporter
    from src.utils.date_tools import DateUtils
    from src.strategies.f_lao_model import load_ths_history

except ImportError as e:
    print(f"{Fore.RED}❌ 关键模块缺失: {e}")
    sys.exit(1)


class PoolGeneratorV3:
    def __init__(self):
        self.pro = TushareClient.get_pro()
        self.fetcher = TushareFetcher()
        self.md_manager = MarketDataManager()

        # ✅ 使用策略管理器
        self.strategy_manager = StrategyManager()

        # ✅ 使用对象列表
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

        index_data = self.fetcher.fetch_market_index(target_date)
        self.md_manager.update_indices(index_data)

        # ✨ 获取的是 Stock 对象列表
        self.all_data = self.fetcher.fetch_daily_full(target_date)
        if not self.all_data:
            print(f"{Fore.RED}❌ 数据拉取失败")
            return False

        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(target_date)
        self.md_manager.update_stats(ths_stats)

        # 计算Top50 (现在 all_data 是对象列表)
        if self.all_data:
            amounts = sorted([s.amount for s in self.all_data], reverse=True)
            if len(amounts) > 50:
                self.top_amount_threshold = amounts[50]
                print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 加载上下文
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

        # ✨ 统一加载策略
        self.strategy_manager.load_strategies(self.context)

        return True

    def run_pipeline(self):
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V3.1 Domain)...")

        tagger = StockTagger(self.top_amount_threshold)
        results_pool = []

        # 遍历 Stock 对象
        for stock in self.all_data:
            if 'ST' in stock.name.upper(): continue

            # 1. 执行策略 (管理器托管)
            # Stock对象有 __getitem__，所以即使策略代码还没改，也能跑
            hit_tags = self.strategy_manager.execute_all(stock)

            # 2. 打标 (Tagger 需要 dict 还是 object?
            # 如果 Tagger 也是旧的，stock对象兼容字典访问，应该也没问题)
            final_tag_str, is_selected, zt_type = tagger.get_tags(stock, hit_tags)

            if is_selected:
                # 回写属性
                stock.limit_type = zt_type
                stock.add_tag(final_tag_str)  # 其实 tags 已经在 to_dict 里处理了
                stock.tags = [final_tag_str]  # 强制覆盖用于导出

                # 转为字典用于导出
                item_dict = stock.to_dict()

                # 补充字段兼容性 (Exporter可能需要这些旧字段)
                item_dict['link_dragon'] = TextUtils.get_link_dragon(stock.code)

                results_pool.append(item_dict)

        # 补充风险数据
        self._enrich_risk_data(results_pool)

        # 分析阶段 (仍然需要 stats)
        # 这里的 analyze_phase 如果需要遍历 pool，现在 pool 是 dict 列表，所以没问题
        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(DateUtils.get_smart_trading_date(self.pro))
        phase_info = MarketAnalyzer.analyze_phase(results_pool, ths_stats)
        self.md_manager.update_stats(phase_info)

        print(f"\n{Fore.YELLOW}{self.md_manager.get_formatted_summary()}")
        ResultExporter.export_pool(results_pool)

    def _enrich_risk_data(self, pool):
        for p in pool:
            # p 是字典
            info = self.risk_map.get(p['name'], {'risk_level': '🟢 Safe'})
            p.update(info)


if __name__ == "__main__":
    generator = PoolGeneratorV3()
    generator.run_pipeline()