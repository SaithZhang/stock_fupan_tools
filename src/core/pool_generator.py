# ==============================================================================
# 🏭 策略工厂 (src/core/pool_generator.py)
# Version: 2.0 (Refactored) | 架构模式: Pipeline + Strategy
# 职责：数据加载 -> 策略调度 -> 结果聚合 -> 文件导出
# ==============================================================================

import pandas as pd
import os
import shutil
import json
import sys
from datetime import datetime
from colorama import init, Fore
from typing import List, Dict, Optional

# --- 1. 基础环境设置 ---
init(autoreset=True)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

# --- 2. 模块导入 ---
try:
    # 2.1 核心配置与工具
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils

    # 2.2 数据层
    from src.data.loader import SystemDataLoader
    from src.data.market import MarketAnalyzer, TechnicalAnalyzer
    # 原始数据加载 (假设这些文件在 src 根目录或路径已正确设置)
    from data_loader import get_merged_data, load_yesterday_ths_data
    from market_data import MarketDataManager

    # 2.3 策略层
    from src.strategies.base import BaseStrategy
    from src.strategies.sentiment import IdentityStrategy, LHBStrategy
    from src.strategies.technical import TrendStrategy, ReboundStrategy, DDDStrategy

    # 2.4 可选模块 (筹码分析)
    try:
        from tools.chip_analyzer import get_chip_metrics, generate_chip_tag

        HAS_CHIP_MODULE = True
    except ImportError:
        HAS_CHIP_MODULE = False

except ImportError as e:
    print(f"{Fore.RED}❌ 严重错误: 核心模块导入失败。请检查目录结构。")
    print(f"详情: {e}")
    sys.exit(1)


# ================= 3. 主核心类 =================

class PoolGenerator:
    def __init__(self):
        self.strategies: List[BaseStrategy] = []
        self.all_data = []
        self.yest_full_data = {}
        self.md_manager = None
        self.risk_map = {}

        # 上下文数据 (用于传递给策略)
        self.context = {
            'holdings': {},
            'f_lao': {},
            'manual': {},
            'broken_pool': {},
            'lhb_codes': set(),
            'seat_map': {},
            'history': {}
        }

    def load_resources(self) -> bool:
        """资源加载阶段：准备所有数据原料"""
        print(f"{Fore.CYAN}📥 [1/4] 正在加载数据资源...")

        # 1. 基础行情
        self.all_data = get_merged_data()
        if not self.all_data:
            print(f"{Fore.RED}❌ 基础行情数据为空")
            return False

        # 2. 昨天数据 (用于计算竞价和溢价)
        self.yest_full_data = load_yesterday_ths_data()

        # 3. 系统/策略数据 (使用 SystemDataLoader)
        self.context['holdings'] = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.context['f_lao'] = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.context['manual'] = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.context['broken_pool'] = SystemDataLoader.load_yesterday_pool()
        self.context['lhb_codes'], self.context['seat_map'] = SystemDataLoader.load_lhb_info()
        self.risk_map = SystemDataLoader.load_risk_data()

        # 4. 历史K线 (用于 TrendStrategy)
        # 修改点：指向 src.strategies 目录
        from src.strategies.f_lao_model import load_ths_history
        print(f"{Fore.MAGENTA}   正在加载历史K线 (Last 30 days)...")
        self.context['history'] = load_ths_history(Config.THS_DIR, days=30)

        # 5. 大盘数据
        self.md_manager = MarketDataManager(Config.DAPAN_DIR)
        self.md_manager.load_data()

        # --- 初始化策略流水线 ---
        # 依赖注入：将数据传给策略对象
        self.strategies = [
            IdentityStrategy(self.context['holdings'], self.context['f_lao'], self.context['manual']),
            LHBStrategy(self.context['lhb_codes'], self.context['seat_map']),
            TrendStrategy(self.context['history']),
            ReboundStrategy(self.context['broken_pool']),
            DDDStrategy()
        ]

        print(f"   ✅ 数据加载完毕。策略链长度: {len(self.strategies)}")
        return True

    def run_pipeline(self):
        """执行阶段：遍历股票，流转策略"""
        if not self.load_resources(): return

        print(f"{Fore.CYAN}⚙️ [2/4] 正在执行策略流水线...")

        # 计算市场概况
        market_stats = MarketAnalyzer.calculate_stats(self.all_data, self.yest_full_data)
        self.md_manager.update_extra_stats(market_stats)

        results_pool = []

        for item in self.all_data:
            processed_item = self._process_single_item(item)
            if processed_item:
                results_pool.append(processed_item)

        # 补充风险数据
        self._enrich_risk_data(results_pool)

        # 市场情绪判定
        phase_info = MarketAnalyzer.analyze_phase(results_pool, market_stats)
        market_stats.update(phase_info)

        self._print_market_summary(phase_info, len(results_pool))
        self._export_data(results_pool, market_stats)

    def _process_single_item(self, item: Dict) -> Optional[Dict]:
        """单只股票的处理流水线"""
        code = str(item['code'])
        name = item['name']

        if 'ST' in name.upper(): return None

        # --- 1. 运行所有策略 ---
        hit_tags = []
        for strategy in self.strategies:
            tags = strategy.run(item)
            if tags: hit_tags.extend(tags)

        # --- 2. 基础涨停/炸板标签补全 ---
        # (这部分逻辑简单且通用，保留在主流程或单独的 BasicStrategy 均可，此处保留在主流程)
        is_zt = item.get('is_zt') or (item.get('today_pct', 0) >= 9.8)
        if is_zt:
            limit_days = item.get('limit_days', 0) + 1
            zt_tag = f"{limit_days}板" + ("/回封" if item.get('open_num', 0) > 0 else "")
            hit_tags.append(zt_tag)

        # 大额补录
        if (item.get('amount', 0) > 20_0000_0000 * 10) and item.get('today_pct', 0) > 0:
            # 20亿且红盘，防止漏网
            pass  # 此时 hit_tags 为空，但在下面判断 is_selected 时，如果想强制收录需加标签
            # 这里维持原逻辑：只根据 hit_tags 判断

        # --- 3. 筛选判定 ---
        # 只要有任何策略命中标签，或者它是高标(>=2板)，就保留
        is_selected = len(hit_tags) > 0

        # 特殊情况：如果是 5日线低吸，必须显式命中
        # 特殊情况：如果是连板高标，即使没策略命中也要看一眼形态
        if item.get('limit_days', 0) >= 2:
            tech_tags, _ = TechnicalAnalyzer.calculate_indicators(self.context['history'].get(code),
                                                                  item.get('price', 0))
            if tech_tags: hit_tags.extend(tech_tags)

        if not is_selected and item.get('limit_days', 0) < 2:
            return None

        # --- 4. 高级分析 (筹码) - 仅对入围者执行 ---
        # 只有特定的入围者才跑昂贵的筹码分析
        needs_chip = (code in self.context['holdings']) or \
                     (code in self.context['broken_pool']) or \
                     (item.get('limit_days', 0) >= 3)

        if HAS_CHIP_MODULE and needs_chip:
            print(f"   🔎 筹码分析: {name} ...", end="")
            c_metrics = get_chip_metrics(code)
            if c_metrics:
                c_tag = generate_chip_tag(c_metrics)
                if c_tag:
                    hit_tags.append(c_tag)
                    print(f" {Fore.YELLOW}Tag: {c_tag}")
                else:
                    print(" (无特征)")
            else:
                print(" (跳过)")

        # --- 5. 最终组装 ---
        # 5.1 标签去重与概念提取
        raw_tag_str = str(item.get('tag', ''))  # 原始数据的tag
        manual_cleaned = ""
        # (注意：这里简化了逻辑。如果需要精细的 manual_cleaned_tag 用于概念去重，
        #  可以从 IdentityStrategy 返回结果中解析，或者简单处理)

        local_concepts = TextUtils.get_core_concepts_local(name, raw_tag_str)
        unique_concepts = TextUtils.get_unique_concepts(manual_cleaned, local_concepts)
        if unique_concepts: hit_tags.append(unique_concepts)

        # 5.2 涨停形态判定
        shape_tags, zt_type = TechnicalAnalyzer.check_special_shape(item)
        if zt_type: hit_tags.append(f"[{zt_type}]")
        hit_tags.extend(shape_tags)

        # 5.3 去重并生成字符串
        final_tag_str = "/".join(sorted(list(set(hit_tags)))).replace('//', '/')

        # 5.4 计算竞价占比
        yest_item = self.yest_full_data.get(code)
        call_auc_ratio = 0.0
        if yest_item and yest_item.get('amount', 0) > 0:
            call_auc_ratio = item.get('call_auction_amount', 0) / yest_item['amount']

        return {
            'sina_code': TextUtils.format_sina_code(code),
            'name': name,
            'tag': final_tag_str,
            'amount': item.get('amount', 0),
            'last_amount': yest_item.get('amount', 0) if yest_item else 0,
            'today_pct': item.get('today_pct', 0),
            'turnover': item.get('turnover', 0),
            'open_pct': item.get('open_pct', 0),
            'price': item.get('price', 0),
            'pct_10': item.get('pct_10', 0),
            'link_dragon': TextUtils.get_link_dragon(code),
            'vol': item.get('vol', 0),
            'vol_prev': item.get('vol_prev', 0),
            'vol_ratio': item.get('vol_ratio', 0),
            'code': code,
            'call_auction_ratio': round(call_auc_ratio, 3),
            'limit_up_type': zt_type
        }

    def _enrich_risk_data(self, pool: List[Dict]):
        """[3/4] 补充异动风险数据"""
        matches = 0
        for p in pool:
            info = self.risk_map.get(p['name'], {
                'risk_level': '🟢 Safe', 'risk_msg': '-', 'risk_rule': '',
                'trigger_next': '-', 'deviation_val_10d': 0.0, 'deviation_val_30d': 0.0
            })
            p.update(info)
            if p['name'] in self.risk_map: matches += 1
        print(f"   ✅ 风险数据匹配成功: {matches} 条")

    def _export_data(self, pool: List[Dict], market_stats: Dict):
        """[4/4] 导出结果文件"""
        if not pool:
            print(f"{Fore.RED}❌ 结果池为空，跳过导出")
            return

        print(f"{Fore.CYAN}💾 [4/4] 正在导出数据...")
        df = pd.DataFrame(pool)
        df.sort_values(by='amount', ascending=False, inplace=True)

        # 确保列存在
        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover',
                'risk_level', 'risk_msg', 'trigger_next', 'call_auction_ratio',
                'limit_up_type', 'link_dragon', 'code']
        # 补全缺失列
        for c in cols:
            if c not in df.columns: df[c] = ""

        # 动态文件名
        date_str = datetime.now().strftime("%Y%m%d")
        dated_path = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_{date_str}.csv')
        latest_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')

        df.to_csv(dated_path, index=False, encoding='utf-8-sig')
        shutil.copyfile(dated_path, latest_path)

        # 导出 JSON
        try:
            final_json = self.md_manager.get_summary() if self.md_manager else {}
            final_json.update(market_stats)
            json_path = os.path.join(Config.OUTPUT_DIR, f'market_sentiment_{date_str}.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(final_json, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ JSON导出警告: {e}")

        print(f"\n{Fore.GREEN}🎉 离线复盘完成！生成标的: {len(pool)} 只")
        print(f"📄 文件路径: {latest_path}")

    def _print_market_summary(self, phase_info, pool_size):
        print(f"\n{Fore.YELLOW}📊 市场状态判定: {phase_info['phase']}")
        print(f"   💡 建议: {phase_info['action_guide']}")
        print(f"   🔥 领涨: {phase_info['top_sectors']}")
        print(f"   📈 入池: {pool_size} 只")


if __name__ == "__main__":
    generator = PoolGenerator()
    generator.run_pipeline()