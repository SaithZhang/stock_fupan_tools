# ==============================================================================
# 📺 竞价监控 (src/monitors/call_auction_screener.py)
# Version: 4.0 (Tushare & THS Concept Integration)
# 核心功能：竞价排序 + 弱转强识别 + 实时板块风口(基于同花顺映射)
# ==============================================================================

import os
import sys
import time
import argparse
import pandas as pd
import json
import re
from colorama import init, Fore, Style, Back

# --- 环境设置 ---
init(autoreset=True)
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

try:
    from src.config.settings import Config
    from src.data.realtime import TencentRealtime
    from src.strategies.auction import AuctionStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class AuctionApp:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.strategy_pool = {}
        self.holdings = set()
        self.concept_map = {}  # 新增：板块映射表
        self.realtime_api = TencentRealtime()
        self.analyzer = AuctionStrategy()

        self._load_resources()

    def _load_resources(self):
        """加载策略池、持仓和板块映射"""
        # 1. 加载持仓
        if os.path.exists(Config.HOLDINGS_PATH):
            with open(Config.HOLDINGS_PATH, 'r', encoding='utf-8') as f:
                self.holdings = {line.strip().split()[0] for line in f if line.strip()}

        # 2. 加载策略池
        pool_path = os.path.join(project_root, 'data', 'output', 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, dtype={'code': str})
                self.strategy_pool = df.set_index('code').to_dict('index')
                if self.test_mode:
                    print(f"{Fore.GREEN}✅ [测试模式] 已加载策略池: {len(self.strategy_pool)} 只标的")
            except Exception as e:
                print(f"{Fore.RED}❌ 策略池加载失败: {e}")
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到策略池文件: {pool_path}")

        # 3. [核心新增] 加载同花顺板块映射
        map_path = os.path.join(project_root, 'data', 'output', 'ths_concept_map.json')
        if os.path.exists(map_path):
            try:
                with open(map_path, 'r', encoding='utf-8') as f:
                    self.concept_map = json.load(f)
                print(f"{Fore.GREEN}✅ 已加载板块映射: {len(self.concept_map)} 条数据")
            except Exception as e:
                print(f"{Fore.RED}❌ 板块映射加载失败: {e}")
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到板块映射文件 (请先运行 pool_generator_tushare.py)")

    def _format_amt(self, amt):
        if amt > 100000000:
            return f"{Fore.RED}{amt / 100000000:.1f}亿{Fore.RESET}"
        elif amt > 10000000:
            return f"{Fore.YELLOW}{int(amt / 10000)}万{Fore.RESET}"
        else:
            return f"{int(amt / 10000)}万"

    def _parse_tags(self, tag_str):
        """
        解析标签 (V4.0 极简版)
        只负责提取 '热度排名' 和 '主力图标'，板块不再靠猜，直接查表
        """
        if not isinstance(tag_str, str): return 999, ""

        # 1. 提取热度 (TopN)
        hot_match = re.search(r'🔥Top(\d+)', tag_str)
        hot_rank = int(hot_match.group(1)) if hot_match else 999

        # 2. 提取主力图标
        icons = []
        if '🏢' in tag_str: icons.append(f"{Fore.YELLOW}🏢{Fore.RESET}")
        if '🐉' in tag_str and '玄学' not in tag_str: icons.append(f"{Fore.CYAN}🐉{Fore.RESET}")

        return hot_rank, "".join(icons)

    def _scan_once(self):
        codes = list(self.strategy_pool.keys())
        if not codes: return

        # 获取实时数据
        realtime_data = {}
        batch_size = 80

        # 仅在第一次或调试时打印进度
        if self.test_mode:
            print(f"正在尝试获取 {len(codes)} 只标的的数据...")

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            try:
                data = self.realtime_api.get_realtime_data(batch)
                if data:
                    realtime_data.update(data)
            except Exception as e:
                pass  # 生产环境静默失败，避免刷屏

        if self.test_mode:
            print(f"📊 最终获取到 {len(realtime_data)} 条实时数据")

        results = []

        # --- 实时板块热度统计器 ---
        # 格式: {'🔥手机游戏': [2.5, 3.1], '银行': [0.1, 0.2]}
        sector_realtime_stats = {}

        for code, row in realtime_data.items():
            pool_info = self.strategy_pool.get(code, {})
            name = row['name']

            # --- 1. 获取精准板块 (查字典) ---
            # 格式可能为 "🔥手机游戏 | 软件服务" 或 "银行"
            full_concept = self.concept_map.get(code, "其他")

            # 核心逻辑：取 "|" 前面的部分作为核心板块
            # 如果是 "🔥手机游戏 | ...", sector 就是 "🔥手机游戏"
            # 如果是 "银行", sector 就是 "银行"
            sector = full_concept.split('|')[0].strip()

            # 基础数据处理
            pre_close = float(pool_info.get('price', row['pre_close']))
            price = float(row['price'])
            if price <= 0: price = pre_close
            if pre_close <= 0: pre_close = 1.0

            auc_pct = (price - pre_close) / pre_close * 100
            auc_amt = float(row['amount'])

            if self.test_mode and auc_amt > 1000000000: auc_amt = auc_amt / 50

            # 解析热度和主力 (从 CSV Tag 中)
            tag_str = str(pool_info.get('tag', ''))
            hot_rank, smart_money_str = self._parse_tags(tag_str)

            # --- 2. 收集板块数据 ---
            # 排除 ST, 排除 '其他'
            if "ST" not in name and sector != "其他":
                if sector not in sector_realtime_stats:
                    sector_realtime_stats[sector] = []
                sector_realtime_stats[sector].append(auc_pct)

            # 策略分析
            yest_amt = float(pool_info.get('amount', 0))
            ratio = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0
            yest_pct = float(pool_info.get('pct', 0))
            is_broken = '炸板' in tag_str or '烂板' in tag_str

            ctx = {'yest_pct': yest_pct, 'auc_amt': auc_amt, 'yest_amt': yest_amt,
                   'yest_tag': tag_str, 'is_broken': is_broken}
            decision, color_code = self.analyzer.analyze(auc_pct, ratio, ctx)

            # 评分
            score = auc_amt
            if '核反转' in decision: score += 100_000_000_000
            if code in self.holdings: score += 50_000_000_000
            if '弱转强' in decision: score += 10_000_000_000 if (hot_rank <= 50) else 1_000_000_000

            # 显示处理
            name_display = name
            if code in self.holdings:
                name_display = f"{Back.BLUE}{Fore.WHITE}[持]{name}{Style.RESET_ALL}"
            elif hot_rank <= 50:
                name_display = f"{Fore.RED}🔥{name}{Fore.RESET}"

            results.append({
                'code': code,
                'name_display': name_display,
                'sector': sector,  # 使用清洗后的核心板块
                'hot_rank': hot_rank,
                'hot_str': f"Top{hot_rank}" if hot_rank < 200 else "",
                'auc_pct': auc_pct,
                'auc_amt': auc_amt,
                'auc_amt_str': self._format_amt(auc_amt),
                'status': f"{color_code}{decision}{Style.RESET_ALL}",
                'smart_money': smart_money_str,
                'score': score,
                'raw_auc_amt': auc_amt
            })

        results.sort(key=lambda x: x['score'], reverse=True)

        if not self.test_mode:
            os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n🚀 竞价监控 V4.0 (Tushare引擎) | 标的: {len(results)}")

        # --- 打印 9:25 实时风口 ---
        print(f"{Back.WHITE}{Fore.BLACK} 📊 9:25 实时风口 (基于同花顺概念映射) {Style.RESET_ALL}")

        sector_ranking = []
        for sec, pcts in sector_realtime_stats.items():
            if len(pcts) >= 2:  # 至少2只才算
                avg_pct = sum(pcts) / len(pcts)
                up_count = len([p for p in pcts if p > 0])
                sector_ranking.append({'name': sec, 'avg': avg_pct, 'count': len(pcts), 'up': up_count})

        sector_ranking.sort(key=lambda x: x['avg'], reverse=True)

        top_str = ""
        for i, s in enumerate(sector_ranking[:6]):
            # 如果是热门概念（带🔥），用红色高亮
            name_show = s['name']
            if "🔥" in name_show:
                name_show = f"{Fore.YELLOW}{name_show}{Fore.RESET}"

            color = Fore.RED if s['avg'] > 1.5 else (Fore.MAGENTA if s['avg'] > 0 else Fore.GREEN)
            top_str += f"{i + 1}.{name_show}:{color}{s['avg']:.2f}%{Fore.RESET}({s['up']}/{s['count']})  "
        print(f"🏆 领涨: {top_str}")
        print("-" * 110)

        # 列表表头
        print(f"{'代码':<8}{'名称':<14}{'核心板块':<14}{'竞价%':<10}{'金额':<10}{'状态/决策':<16}{'主力/热度'}")
        print("-" * 110)

        count = 0
        for r in results:
            if not self.test_mode:
                if r['raw_auc_amt'] < 5000000 and "[持]" not in r['name_display'] and r[
                    'hot_rank'] > 50 and "弱转强" not in r['status'] and "核反转" not in r['status']:
                    continue
            if count >= 30: break

            # 组合最后一列
            info_tail = f"{r['hot_str']} {r['smart_money']}"

            print(f"{r['code']:<8}{r['name_display']:<23}{r['sector']:<16}"
                  f"{self._color_pct(r['auc_pct']):<14}{r['auc_amt_str']:<12}"
                  f"{r['status']:<25}{info_tail}")
            count += 1
        print("=" * 110)

    def run(self):
        if self.test_mode:
            print(f"{Fore.CYAN}🧪 [测试模式] 仅运行一次扫描，不过滤低金额...")
            self._scan_once()
            print(f"{Fore.CYAN}🧪 测试结束")
            return

        print(f"{Fore.CYAN}🦅 竞价监控启动 (V4.0)... 按 Ctrl+C 退出")
        while True:
            try:
                self._scan_once()
                time.sleep(3)
            except KeyboardInterrupt:
                print("\n监控结束")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)

    def _color_pct(self, pct):
        if pct > 0:
            return f"{Fore.RED}+{pct:.2f}%{Fore.RESET}"
        elif pct < 0:
            return f"{Fore.GREEN}{pct:.2f}%{Fore.RESET}"
        else:
            return f"{pct:.2f}%"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='运行一次测试模式')
    args = parser.parse_args()

    app = AuctionApp(test_mode=args.test)
    app.run()