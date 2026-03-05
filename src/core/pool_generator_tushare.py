# ==============================================================================
# 🏭 策略工厂 V3.5 (src/core/pool_generator_tushare.py)
# Version: 3.5 (Tag Fusion Fix - Preserve Fetcher Tags + Manual Date)
# ==============================================================================

import os
import sys
import argparse
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
    from src.core.filter import StockFilter

except ImportError as e:
    print(f"{Fore.RED}❌ 关键模块缺失: {e}")
    sys.exit(1)


class PoolGeneratorV3:
    def __init__(self, target_date: str = None):
        self.pro = TushareClient.get_pro()
        self.fetcher = TushareFetcher()
        self.md_manager = MarketDataManager()
        self.strategy_manager = StrategyManager()
        self.filter = StockFilter()

        self.all_data: List[Stock] = []
        self.context = {
            'holdings': {}, 'f_lao': {}, 'manual': {}, 'broken_pool': {},
            'lhb_codes': set(), 'seat_map': {}, 'history': {}
        }
        self.top_amount_threshold = 0
        self.risk_map = {}

        # 记录目标日期
        self.target_date = target_date

    def load_resources(self) -> bool:
        print(f"{Fore.CYAN}📥 [1/4] Tushare Pro 资源加载...")

        # 核心逻辑：如果有手动传入日期则使用，否则自动推算
        if not self.target_date:
            self.target_date = DateUtils.get_smart_trading_date(self.pro)

        print(f"   📅 锁定复盘日期: {Fore.YELLOW}{self.target_date}{Fore.RESET}")

        # 1. 指数
        index_data = self.fetcher.market.fetch_index(self.target_date)
        self.md_manager.update_indices(index_data)

        # 2. 全市场数据 (个股流水线)
        self.all_data = self.fetcher.stocks.run(self.target_date)

        if not self.all_data:
            print(f"{Fore.RED}❌ 数据拉取失败")
            return False

        # 3. 同花顺概览
        ths_stats = self.fetcher.market.fetch_limit_stats(self.target_date)
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
            df_lhb = self.pro.top_list(trade_date=self.target_date)
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

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V3.5 Tag Fusion)...")

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

            # 获取策略标签 (Hit Tags)
            tag_str = tag_map.get(stock.ts_code, "")
            hit_tags = tag_str.split(" | ") if tag_str else []

            # 过滤器检查
            if not self.filter.check(stock, hit_tags, self.context):
                continue

            # 🔥 核心修复：备份 Fetcher 阶段获取的标签 (如热度、游资)
            # Stock 对象在 fetcher 中可能已经有了 tags 属性 (list)
            fetcher_tags = stock.tags if hasattr(stock, 'tags') and stock.tags else []

            # 计算 Tagger 标签 (技术面/概念/连板)
            final_tag_str, is_selected, zt_type = tagger.get_tags(stock, hit_tags)

            if is_selected:
                stock.limit_type = zt_type

                # 🔥 核心修复：标签融合 (Fusion)
                # 将 fetcher_tags 追加到 final_tag_str 后面，避免覆盖
                fusion_tags = []
                if final_tag_str: fusion_tags.append(final_tag_str)

                for t in fetcher_tags:
                    # 去重：如果 final_tag_str 里已经有了，就不加了
                    if t and t not in final_tag_str:
                        fusion_tags.append(t)

                # 更新最终标签字符串
                merged_tag_str = "/".join(fusion_tags)
                stock.add_tag(merged_tag_str)
                stock.tags = [merged_tag_str]  # 确保导出时使用的是融合后的标签

                item_dict = stock.to_dict()
                item_dict['link_dragon'] = TextUtils.get_link_dragon(stock.code)

                risk_info = self.risk_map.get(stock.name, {'risk_level': '🟢 Safe'})
                item_dict.update(risk_info)

                results_pool.append(item_dict)
            else:
                filtered_count += 1

        print(f"   🧹 已过滤弱势/非活跃标的: {len(self.all_data) - len(results_pool)} 只")
        print(f"   💎 最终入池: {len(results_pool)} 只")

        # 获取统计数据 (用于大盘分析)
        # ⚠️ 修复点：这里原来硬编码了 DateUtils，现替换为统一的 self.target_date
        ths_stats = self.fetcher.market.fetch_limit_stats(self.target_date)

        phase_info = MarketAnalyzer.analyze_phase(results_pool, ths_stats)
        self.md_manager.update_stats(phase_info)

        print(f"\n{Fore.YELLOW}{self.md_manager.get_formatted_summary()}")
        ResultExporter.export_pool(results_pool)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="策略工厂 V3.5")
    parser.add_argument('--date', type=str, help='手动指定复盘日期，格式: YYYYMMDD, 例如 20260305', default=None)
    args = parser.parse_args()

    # 传入解析到的日期（如果没传就是 None）
    generator = PoolGeneratorV3(target_date=args.date)
    generator.run_pipeline()