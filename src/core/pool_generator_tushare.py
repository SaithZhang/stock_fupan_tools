# ==============================================================================
# 🏭 策略工厂 V3.0 (src/core/pool_generator_tushare.py)
# Version: 3.0 (Refactored: Uses TushareFetcher)
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
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    # ------------------- 核心模块导入 -------------------
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
    from src.data.market import MarketAnalyzer
    from src.data.loader import SystemDataLoader

    # ✨ 新的数据源模块
    from src.data.tushare_source.client import TushareClient
    from src.data.tushare_source.fetcher import TushareFetcher
    from src.data.market_data import MarketDataManager

    # ✨ 模块化组件
    from src.core.stock_tagger import StockTagger
    from src.data.exporter import ResultExporter
    from src.utils.date_tools import DateUtils

    # ------------------- 策略模块导入 -------------------
    from src.strategies.base import BaseStrategy
    from src.strategies.sentiment import IdentityStrategy, LHBStrategy
    from src.strategies.technical import TrendStrategy, ReboundStrategy, DDDStrategy, SidewaysChipStrategy
    from src.strategies.f_lao_model import load_ths_history

except ImportError as e:
    print(f"{Fore.RED}❌ 关键模块缺失: {e}")
    sys.exit(1)


class PoolGeneratorV2:
    def __init__(self):
        self.strategies: List[BaseStrategy] = []
        self.all_data = []

        # 初始化核心组件
        self.pro = TushareClient.get_pro()  # 获取连接
        self.fetcher = TushareFetcher()  # 数据抓取器
        self.md_manager = MarketDataManager()  # 数据展示器

        self.context = {
            'holdings': {}, 'f_lao': {}, 'manual': {}, 'broken_pool': {},
            'lhb_codes': set(), 'seat_map': {}, 'history': {}
        }
        self.top_amount_threshold = 0
        self.risk_map = {}

    def load_resources(self) -> bool:
        print(f"{Fore.CYAN}📥 [1/4] Tushare Pro 资源加载...")

        # 1. 智能锁定日期
        target_date = DateUtils.get_smart_trading_date(self.pro)
        print(f"   📅 锁定复盘日期: {Fore.YELLOW}{target_date}{Fore.RESET}")

        # 2. 获取大盘指数 -> 注入展示器
        index_data = self.fetcher.fetch_market_index(target_date)
        self.md_manager.update_indices(index_data)

        # 3. 获取全市场数据 (日线+竞价+同花顺状态)
        self.all_data = self.fetcher.fetch_daily_full(target_date)
        if not self.all_data:
            print(f"{Fore.RED}❌ 数据拉取失败，流程终止")
            return False

        # 4. 获取权威涨跌停统计 -> 注入展示器
        # (虽然 fetch_daily_full 内部也查了，但为了拿 pure stats，这里再调一次，或者让 fetcher 返回 stats)
        # 为简单起见，这里再调用一次专门获取统计的方法，开销很小
        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(target_date)
        self.md_manager.update_stats(ths_stats)

        # 5. 计算人气门槛 (Top50 成交额)
        if self.all_data:
            amounts = sorted([x['amount'] for x in self.all_data], reverse=True)
            if len(amounts) > 50:
                self.top_amount_threshold = amounts[50]
                print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 6. 加载本地配置
        self.context['holdings'] = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.context['f_lao'] = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.context['manual'] = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.context['broken_pool'] = SystemDataLoader.load_yesterday_pool()
        self.risk_map = SystemDataLoader.load_risk_data()

        # 7. 加载龙虎榜 (使用 fetcher 里的连接，或者直接调用 pro)
        try:
            df_lhb = self.pro.top_list(trade_date=target_date)
            if not df_lhb.empty:
                self.context['lhb_codes'] = set(df_lhb['ts_code'].apply(lambda x: x.split('.')[0]).tolist())
        except:
            pass

        _, local_seat_map = SystemDataLoader.load_lhb_info()
        self.context['seat_map'] = local_seat_map

        # 8. 加载历史K线
        self.context['history'] = load_ths_history(Config.THS_DIR, days=30)

        # 9. 初始化策略
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

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V3.0)...")

        tagger = StockTagger(self.top_amount_threshold)

        results_pool = []
        for item in self.all_data:
            processed_item = self._process_single_item(item, tagger)
            if processed_item: results_pool.append(processed_item)

        # 补充风险数据
        self._enrich_risk_data(results_pool)

        # 2. 分析市场阶段
        # 注意: analyze_phase 需要 market_stats 字典，我们可以直接从 md_manager 拿，或者重新计算
        # 这里为了简单，我们用 fetcher 拿到的 ths_stats 传进去
        ths_stats, _ = self.fetcher.fetch_ths_limit_stats(DateUtils.get_smart_trading_date(self.pro))
        phase_info = MarketAnalyzer.analyze_phase(results_pool, ths_stats)

        # 将阶段信息注入 Manager
        self.md_manager.update_stats(phase_info)

        # 3. 打印最终的大盘总结
        print(f"\n{Fore.YELLOW}{self.md_manager.get_formatted_summary()}")

        # 4. 导出
        ResultExporter.export_pool(results_pool)

    def _process_single_item(self, item: Dict, tagger: StockTagger) -> Optional[Dict]:
        """处理单只股票"""
        code = item['code']
        if 'ST' in str(item['name']).upper(): return None

        # 1. 运行策略
        strategies_hit_tags = []
        for strategy in self.strategies:
            tags = strategy.run(item)
            if tags: strategies_hit_tags.extend(tags)

        # 2. 打标
        final_tag_str, is_selected, zt_type = tagger.get_tags(item, strategies_hit_tags)

        if not is_selected: return None

        # 3. 组装
        # 注意：fetcher 返回的数据 key 可能和之前稍有不同，这里做统一适配
        auc_ratio = item.get('auction_ratio', 0.0)
        return {
            'sina_code': item['sina_code'],
            'name': item['name'],
            'tag': final_tag_str,
            'amount': item.get('amount', 0),
            'last_amount': 0,  # 新接口暂未返回昨日成交额，暂置0
            'today_pct': item.get('today_pct', 0),
            'turnover': item.get('turnover', 0),
            'open_pct': item.get('open_pct', 0),
            'price': item.get('price', 0),
            'pct_10': 0,
            'link_dragon': TextUtils.get_link_dragon(code),
            'vol': 0,  # 策略展示暂时不需要原始 vol
            'vol_ratio': item.get('vol_ratio', 0),
            'code': code,
            'call_auction_ratio': round(auc_ratio * 100, 2),
            'limit_up_type': zt_type,
            'risk_level': 'N/A',
            'limit_days': item.get('limit_days', 0)  # 确保透传连板数
        }

    def _enrich_risk_data(self, pool):
        for p in pool:
            info = self.risk_map.get(p['name'], {'risk_level': '🟢 Safe'})
            p.update(info)


if __name__ == "__main__":
    generator = PoolGeneratorV2()
    generator.run_pipeline()