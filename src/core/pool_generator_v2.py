# ==============================================================================
# 🏭 策略工厂 V2.5 (src/core/pool_generator_v2.py)
# Version: 2.5 (THS Concept Integration)
# ==============================================================================

import pandas as pd
import os
import sys
from datetime import datetime
from colorama import init, Fore
from typing import List, Dict, Optional

init(autoreset=True)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

try:
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
    from src.data.market import MarketAnalyzer, TechnicalAnalyzer

    # 兼容导入 market_data
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

    from src.strategies.base import BaseStrategy
    from src.strategies.sentiment import IdentityStrategy, LHBStrategy
    from src.strategies.technical import TrendStrategy, ReboundStrategy, DDDStrategy, SidewaysChipStrategy
    from src.data.tushare_manager import TushareManager
    from src.data.loader import SystemDataLoader

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
        # 1. 初始化 Tushare (⚠️修改版：适配淘宝代理)
        try:
            import tushare as ts

            # --- 👇 把这里换成你买的 Token 和 代理地址 ---
            # (我也直接把你文件里的填在这里了，方便你直接复制)
            my_token = "e90040a46bc696bd7c69380ab1c13973bb28eb031d013cf00936b97a323f"
            my_proxy_url = "http://lianghua.nanyangqiankun.top"

            # 1. 先用 Token 正常初始化
            self.pro = ts.pro_api(my_token)

            # 2. 🚨【核心步骤】强制修改内部 URL 指向你的代理 🚨
            # 这一步就是你之前能用的关键，必须加上！
            self.pro._DataApi__http_url = my_proxy_url
            self.pro._DataApi__token = my_token  # 既然你之前代码有这行，我们也加上，双重保险

            print(f"{Fore.GREEN}✅ Tushare 接口初始化成功 (已接管代理: {my_proxy_url}){Fore.RESET}")

        except Exception as e:
            self.pro = None
            print(f"{Fore.YELLOW}❌ Tushare 初始化失败，横盘筹码策略将失效: {e}{Fore.RESET}")

    def load_resources(self) -> bool:
        print(f"{Fore.CYAN}📥 [1/4] Tushare Pro 资源加载 (THS Ultimate)...")
        target_date = self.ts_driver.get_trading_date()
        print(f"   📅 目标日期: {target_date}")

        # 1. 拉取数据 (含同花顺涨停/概念/炸板)
        self.all_data = self.ts_driver.fetch_daily_snapshot(target_date)
        if not self.all_data:
            print(f"{Fore.RED}❌ 无数据返回")
            return False

        # 人气门槛计算
        amounts = sorted([x['amount'] for x in self.all_data], reverse=True)
        if len(amounts) > 50:
            self.top_amount_threshold = amounts[50]
            print(f"   💰 人气股门槛(Top50): {self.top_amount_threshold / 100000000:.1f} 亿")

        # 2. 加载本地配置
        self.context['holdings'] = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.context['f_lao'] = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.context['manual'] = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.context['broken_pool'] = SystemDataLoader.load_yesterday_pool()
        self.risk_map = SystemDataLoader.load_risk_data()

        # 3. 大盘与龙虎榜
        self.md_manager = MarketDataManager(Config.DAPAN_DIR)
        self.md_manager.load_data()

        df_lhb = self.ts_driver.fetch_lhb_data(target_date)
        if not df_lhb.empty:
            self.context['lhb_codes'] = set(df_lhb['ts_code'].apply(lambda x: x.split('.')[0]).tolist())

        _, local_seat_map = SystemDataLoader.load_lhb_info()
        self.context['seat_map'] = local_seat_map

        # 4. 历史K线
        self.context['history'] = load_ths_history(Config.THS_DIR, days=30)

        # 5. 策略初始化
        self.strategies = [
            IdentityStrategy(self.context['holdings'], self.context['f_lao'], self.context['manual']),
            LHBStrategy(self.context['lhb_codes'], self.context['seat_map']),
            TrendStrategy(self.context['history']),
            ReboundStrategy(self.context['broken_pool']),
            SidewaysChipStrategy(self.market_data.history_map, self.pro),
            DDDStrategy()
        ]
        return True

    def run_pipeline(self):
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 执行策略 (V2.5)...")
        market_stats = MarketAnalyzer.calculate_stats(self.all_data, self.yest_full_data)
        if self.md_manager: self.md_manager.update_extra_stats(market_stats)

        results_pool = []
        for item in self.all_data:
            processed_item = self._process_single_item(item)
            if processed_item: results_pool.append(processed_item)

        self._enrich_risk_data(results_pool)
        phase_info = MarketAnalyzer.analyze_phase(results_pool, market_stats)
        market_stats.update(phase_info)

        self._print_market_summary(phase_info, len(results_pool))
        self._export_data(results_pool, market_stats)

    def _process_single_item(self, item: Dict) -> Optional[Dict]:
        """
        处理单只股票逻辑 (V2.5 修复版)
        修正：收紧入池标准，防止仅因竞价达标而导致标的过多
        """
        code = item['code']
        name = item['name']
        if 'ST' in name.upper(): return None

        hit_tags = []
        has_strategy_hit = False

        # 1. 运行所有基础策略 (趋势、龙虎榜、持仓、反包等)
        # 如果命中了这些策略，has_strategy_hit 会置为 True
        for strategy in self.strategies:
            tags = strategy.run(item)
            if tags:
                hit_tags.extend(tags)
                has_strategy_hit = True

        # A. 涨停连板标签
        if item.get('is_zt'):
            limit_days = item.get('limit_days', 1)
            zt_tag = f"{limit_days}板"
            hit_tags.append(zt_tag)

        # B. 同花顺概念融合
        ths_desc = item.get('ths_desc', '')
        if ths_desc:
            concepts = ths_desc.split('+')
            cleaned_concepts = "/".join(concepts[:2])
            hit_tags.append(cleaned_concepts)

        # C. 实时炸板识别
        if item.get('is_broken'):
            hit_tags.append("💣炸板")

        # === D. 竞价逻辑分析 (辅助打标，不作为独立入池标准) ===
        auc_ratio = item.get('auction_ratio', 0.0)
        auc_amt = item.get('auc_amt', 0)
        is_zt = item.get('is_zt', False)

        # 1. 竞价爆量标签
        if auc_ratio >= 0.10:
            hit_tags.append("🔥竞价超预期")  # >10%
        elif auc_ratio >= 0.05:
            hit_tags.append("⚡竞价达标")  # >5%

        # 2. 竞价金额过亿 (大资金战场)
        if auc_amt > 100000000:  # 1亿
            hit_tags.append("💰竞价过亿")

        # 3. 弱转强判定 (买点逻辑：竞价强 + 最终涨停)
        if auc_ratio >= 0.05 and is_zt:
            hit_tags.append("🎯疑似弱转强")

        # E. 人气/容量兜底
        is_capacity_stock = (item['amount'] > self.top_amount_threshold) and (item['today_pct'] > 0)
        if is_capacity_stock:
            hit_tags.append("★人气/容量")

        # === 核心筛选逻辑 (收紧标准) ===
        is_selected = False

        # 标准1: 涨停股 (必须入池)
        if item.get('limit_days', 0) >= 1 or is_zt:
            is_selected = True

        # 标准2: 炸板股 (关注后续反包)
        if item.get('is_broken'):
            is_selected = True

        # 标准3: 策略命中 (龙虎榜、趋势、持仓等)
        # 注意：这里利用 has_strategy_hit 标志，排除了仅有竞价tag的情况
        if has_strategy_hit:
            is_selected = True

        # 标准4: 人气/容量核心
        if is_capacity_stock:
            is_selected = True

        # 如果不满足以上任一条件，直接过滤 (解决标的过多的问题)
        if not is_selected:
            return None

        # F. 补充本地概念与形态 (仅对入池标的执行，节省性能)
        local_concepts = TextUtils.get_core_concepts_local(name, str(item.get('tag', '')))
        if local_concepts: hit_tags.append(local_concepts)

        shape_tags, zt_type = TechnicalAnalyzer.check_special_shape(item)
        if zt_type: hit_tags.append(f"[{zt_type}]")
        hit_tags.extend(shape_tags)

        final_tag_str = "/".join(sorted(list(set(hit_tags)))).replace('//', '/')

        return {
            'sina_code': item['sina_code'],
            'name': name,
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
            # 导出百分比格式，方便在表格中查看 (如 5.23 代表 5.23%)
            'call_auction_ratio': round(auc_ratio * 100, 2),
            'limit_up_type': zt_type,
            'risk_level': 'N/A'
        }

    def _enrich_risk_data(self, pool):
        for p in pool:
            info = self.risk_map.get(p['name'], {'risk_level': '🟢 Safe'})
            p.update(info)

    def _export_data(self, pool, market_stats):
        if not pool: return
        df = pd.DataFrame(pool)
        df.sort_values(by='amount', ascending=False, inplace=True)
        date_str = datetime.now().strftime("%Y%m%d")
        path = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_v2_{date_str}.csv')

        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'risk_level']
        for c in cols:
            if c not in df.columns: df[c] = ""

        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f"\n{Fore.GREEN}🎉 V2.5 复盘完成！生成标的: {len(pool)} 只")
        print(f"📄 文件路径: {path}")

    def _print_market_summary(self, phase_info, pool_size):
        print(f"\n{Fore.YELLOW}📊 市场: {phase_info['phase']} | 建议: {phase_info['action_guide']}")


if __name__ == "__main__":
    generator = PoolGeneratorV2()
    generator.run_pipeline()