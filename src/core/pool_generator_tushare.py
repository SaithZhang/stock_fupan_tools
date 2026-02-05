# ==============================================================================
# 🏭 策略工厂 V2.6 (src/core/pool_generator_tushare.py)
# Version: 2.6 (Modular Refactoring: Tagger/Exporter/DateUtils)
# ==============================================================================

import os
import sys
from colorama import init, Fore
from typing import List, Dict, Optional

# 初始化颜色输出
init(autoreset=True)

# 路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

try:
    # ------------------- 核心模块导入 -------------------
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
    from src.data.market import MarketAnalyzer
    from src.data.tushare_manager import TushareManager
    from src.data.loader import SystemDataLoader

    # ✨ 新增模块化组件导入
    from src.core.stock_tagger import StockTagger  # 负责打标逻辑
    from src.data.exporter import ResultExporter  # 负责导出 CSV
    from src.utils.date_tools import DateUtils  # 负责智能日期

    # ------------------- 策略模块导入 -------------------
    from src.strategies.base import BaseStrategy
    from src.strategies.sentiment import IdentityStrategy, LHBStrategy
    from src.strategies.technical import TrendStrategy, ReboundStrategy, DDDStrategy, SidewaysChipStrategy

    # 兼容性导入 MarketDataManager
    try:
        from market_data import MarketDataManager
    except ImportError:
        try:
            from src.data.market_data import MarketDataManager
        except ImportError:
            class MarketDataManager:
                def __init__(self, *a): pass

                def load_data(self): pass

                def update_extra_stats(self, *a): pass

                def get_summary(self): return {}

    # 兼容性导入 load_ths_history
    try:
        from src.strategies.f_lao_model import load_ths_history
    except ImportError:
        def load_ths_history(*args, **kwargs):
            return {}

except ImportError as e:
    print(f"{Fore.RED}❌ 模块导入严重失败: {e}")
    sys.exit(1)


class PoolGeneratorV2:
    def __init__(self):
        self.strategies: List[BaseStrategy] = []
        self.all_data = []
        self.yest_full_data = {}
        self.md_manager = None
        self.risk_map = {}
        self.ts_driver = TushareManager()
        self.context = {
            'holdings': {}, 'f_lao': {}, 'manual': {}, 'broken_pool': {},
            'lhb_codes': set(), 'seat_map': {}, 'history': {}
        }
        self.top_amount_threshold = 0

        # 直接复用 TushareManager 的连接
        self.pro = self.ts_driver.pro
        if not self.pro:
            print(f"{Fore.YELLOW}⚠️ 警告: Tushare Pro 初始化失败，部分策略将自动跳过。")

    def load_resources(self) -> bool:
        print(f"{Fore.CYAN}📥 [1/4] Tushare Pro 资源加载 (THS Ultimate)...")

        # ✅ 使用工具类获取智能日期 (自动处理盘中/盘后/周末/节假日)
        target_date = DateUtils.get_smart_trading_date(self.pro)
        print(f"   📅 锁定复盘日期: {Fore.YELLOW}{target_date}{Fore.RESET}")

        # 1. 拉取数据
        self.all_data = self.ts_driver.fetch_daily_snapshot(target_date)
        if not self.all_data:
            print(f"{Fore.RED}❌ 无数据返回 (日期: {target_date})")
            return False

        # 2. 计算人气门槛 (Top50 成交额)
        amounts = sorted([x['amount'] for x in self.all_data], reverse=True)
        if len(amounts) > 50:
            self.top_amount_threshold = amounts[50]
            print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 3. 加载本地配置
        self.context['holdings'] = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.context['f_lao'] = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.context['manual'] = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.context['broken_pool'] = SystemDataLoader.load_yesterday_pool()
        self.risk_map = SystemDataLoader.load_risk_data()

        # 4. 加载大盘与龙虎榜
        self.md_manager = MarketDataManager(Config.DAPAN_DIR)
        self.md_manager.load_data()

        df_lhb = self.ts_driver.fetch_lhb_data(target_date)
        if not df_lhb.empty:
            self.context['lhb_codes'] = set(df_lhb['ts_code'].apply(lambda x: x.split('.')[0]).tolist())

        _, local_seat_map = SystemDataLoader.load_lhb_info()
        self.context['seat_map'] = local_seat_map

        # 5. 加载历史K线 (用于趋势策略)
        self.context['history'] = load_ths_history(Config.THS_DIR, days=30)

        # 6. 初始化所有策略
        self.strategies = [
            IdentityStrategy(self.context['holdings'], self.context['f_lao'], self.context['manual']),
            LHBStrategy(self.context['lhb_codes'], self.context['seat_map']),
            TrendStrategy(self.context['history']),
            ReboundStrategy(self.context['broken_pool']),
            SidewaysChipStrategy(self.context['history'], self.pro),
            DDDStrategy()
        ]
        return True

    def run_pipeline(self):
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V2.6)...")

        # ✨ 初始化业务逻辑打标器
        tagger = StockTagger(self.top_amount_threshold)

        market_stats = MarketAnalyzer.calculate_stats(self.all_data, self.yest_full_data)
        if self.md_manager: self.md_manager.update_extra_stats(market_stats)

        results_pool = []
        for item in self.all_data:
            # ✨ 核心处理逻辑委托给 process_single_item，并传入 tagger
            processed_item = self._process_single_item(item, tagger)
            if processed_item: results_pool.append(processed_item)

        # 补充风险数据
        self._enrich_risk_data(results_pool)

        # 市场情绪阶段分析
        phase_info = MarketAnalyzer.analyze_phase(results_pool, market_stats)
        self._print_market_summary(phase_info, len(results_pool))

        # ✨ 导出逻辑完全委托给 Exporter
        ResultExporter.export_pool(results_pool)

    def _process_single_item(self, item: Dict, tagger: StockTagger) -> Optional[Dict]:
        """
        处理单只股票：
        1. 运行所有策略获取策略标签。
        2. 调用 StockTagger 获取综合标签 (含竞价、形态、人气等)。
        3. 组装最终数据格式。
        """
        code = item['code']
        if 'ST' in item['name'].upper(): return None

        # 1. 运行策略集合
        strategies_hit_tags = []
        for strategy in self.strategies:
            tags = strategy.run(item)
            if tags: strategies_hit_tags.extend(tags)

        # 2. 调用打标器获取综合标签 ✨
        final_tag_str, is_selected, zt_type = tagger.get_tags(item, strategies_hit_tags)

        # 未入选则直接返回
        if not is_selected: return None

        # 3. 组装返回数据
        auc_ratio = item.get('auction_ratio', 0.0)
        return {
            'sina_code': item['sina_code'],
            'name': item['name'],
            'tag': final_tag_str,
            'amount': item.get('amount', 0),
            'last_amount': 0,
            'today_pct': item.get('today_pct', 0),
            'turnover': item.get('turnover', 0),
            'open_pct': item.get('open_pct', 0),
            'price': item.get('price', 0),
            'pct_10': 0,
            'link_dragon': TextUtils.get_link_dragon(code),
            'vol': item.get('vol', 0),
            'vol_ratio': item.get('vol_ratio', 0),
            'code': code,
            'call_auction_ratio': round(auc_ratio * 100, 2),
            'limit_up_type': zt_type,
            'risk_level': 'N/A'
        }

    def _enrich_risk_data(self, pool):
        for p in pool:
            info = self.risk_map.get(p['name'], {'risk_level': '🟢 Safe'})
            p.update(info)

    def _print_market_summary(self, phase_info, pool_size):
        print(f"\n{Fore.YELLOW}📊 市场: {phase_info['phase']} | 建议: {phase_info['action_guide']}")


if __name__ == "__main__":
    generator = PoolGeneratorV2()
    generator.run_pipeline()