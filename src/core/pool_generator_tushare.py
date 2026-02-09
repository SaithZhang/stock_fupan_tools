# ==============================================================================
# 🏭 策略工厂 V3.2 (src/core/pool_generator_tushare.py)
# Version: 3.2 (Domain Driven & New Strategy Engine)
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

    # ✨ 核心架构升级：引入新版对象和管理器
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

        # ✅ 使用新版策略管理器 (自动加载 technical, sentiment, bolao_chip 等策略)
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

        # 1. 获取大盘指数
        index_data = self.fetcher.fetch_market_index(target_date)
        self.md_manager.update_indices(index_data)

        # 2. ✨ 获取全市场数据 (返回 Stock 对象列表)
        # 包含了：日线、竞价、同花顺涨跌停、筹码分布等
        self.all_data = self.fetcher.fetch_daily_full(target_date)
        if not self.all_data:
            print(f"{Fore.RED}❌ 数据拉取失败")
            return False

        # 3. 获取同花顺概览
        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(target_date)
        self.md_manager.update_stats(ths_stats)

        # 4. 计算Top50成交额门槛
        if self.all_data:
            amounts = sorted([s.amount for s in self.all_data], reverse=True)
            if len(amounts) > 50:
                self.top_amount_threshold = amounts[50]
                print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 5. 加载上下文 (持仓、大佬作业、人工置顶等)
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

        # ❌ 已移除: self.strategy_manager.load_strategies(self.context)
        # 新版 Manager 在 __init__ 中已完成初始化

        return True

    def run_pipeline(self):
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V3.2 New Engine)...")

        # ✨ 步骤 1: 批量运行新策略引擎
        # run_all 返回一个 DataFrame，包含所有计算好的 tags
        df_strategy_result = self.strategy_manager.run_all(self.all_data)

        # 将策略结果转换为字典映射，方便后续 O(1) 查找
        # 结构: {'000001.SZ': "趋势多头 | 筹码突破", ...}
        tag_map = {}
        if not df_strategy_result.empty and 'tag' in df_strategy_result.columns:
            # 确保使用 ts_code 作为索引，因为 Stock 对象里有 ts_code
            tag_map = df_strategy_result.set_index('ts_code')['tag'].to_dict()

        tagger = StockTagger(self.top_amount_threshold)
        results_pool = []

        # ✨ 步骤 2: 保持原有的遍历打标逻辑
        for stock in self.all_data:
            if stock.is_st:
                continue

            # 从策略结果中提取该股票的标签字符串
            tag_str = tag_map.get(stock.ts_code, "")

            # 将字符串 "TagA | TagB" 转回列表 ["TagA", "TagB"] 供 Tagger 使用
            hit_tags = tag_str.split(" | ") if tag_str else []

            # 调用原来的 Tagger 进行最终筛选 (Tagger 内部会结合 context 判断是否保留)
            final_tag_str, is_selected, zt_type = tagger.get_tags(stock, hit_tags)

            if is_selected:
                # 回写属性
                stock.limit_type = zt_type
                stock.add_tag(final_tag_str)
                stock.tags = [final_tag_str]  # 强制覆盖用于导出

                # 转为字典用于导出
                item_dict = stock.to_dict()

                # 补充字段兼容性
                item_dict['link_dragon'] = TextUtils.get_link_dragon(stock.code)

                # 补充策略中计算的特定指标 (如果 item_dict 中没有，可以从 df_strategy_result 补)
                # 例如 winner_rate 等已经在 to_dict 中包含了

                results_pool.append(item_dict)

        # 补充风险数据
        self._enrich_risk_data(results_pool)

        # 分析阶段 (仍然使用 fetcher 获取的 stats)
        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(DateUtils.get_smart_trading_date(self.pro))
        phase_info = MarketAnalyzer.analyze_phase(results_pool, ths_stats)
        self.md_manager.update_stats(phase_info)

        print(f"\n{Fore.YELLOW}{self.md_manager.get_formatted_summary()}")

        # 导出结果
        ResultExporter.export_pool(results_pool)

    def _enrich_risk_data(self, pool):
        for p in pool:
            # p 是字典
            info = self.risk_map.get(p['name'], {'risk_level': '🟢 Safe'})
            p.update(info)


if __name__ == "__main__":
    generator = PoolGeneratorV3()
    generator.run_pipeline()