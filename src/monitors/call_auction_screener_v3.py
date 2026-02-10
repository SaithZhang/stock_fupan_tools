# ==============================================================================
# 📺 竞价监控 (src/monitors/call_auction_screener.py)
# Version: 3.5 (Smart Auction: Hot & Smart Money Integrated)
# 核心功能：竞价排序 + 弱转强识别 + 热度/主力可视化
# ==============================================================================

import os
import sys
import time
import pandas as pd
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
    from src.utils.text_tools import TextUtils
    from src.data.realtime import TencentRealtime
    from src.strategies.auction import AuctionStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class AuctionApp:
    def __init__(self):
        self.strategy_pool = {}
        self.holdings = set()
        self.realtime_api = TencentRealtime()
        self.analyzer = AuctionStrategy()
        # 加载配置
        self._load_resources()

    def _load_resources(self):
        """加载策略池和持仓"""
        # 1. 加载持仓
        if os.path.exists(Config.HOLDINGS_PATH):
            with open(Config.HOLDINGS_PATH, 'r', encoding='utf-8') as f:
                self.holdings = {line.strip().split()[0] for line in f if line.strip()}

        # 2. 加载策略池 (strategy_pool.csv)
        pool_path = os.path.join(project_root, 'data', 'output', 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                # 确保读取 tag 列
                df = pd.read_csv(pool_path, dtype={'code': str})
                # 转为字典: code -> {name, tag, ...}
                self.strategy_pool = df.set_index('code').to_dict('index')
                print(f"{Fore.GREEN}✅ 已加载策略池: {len(self.strategy_pool)} 只标的")
            except Exception as e:
                print(f"{Fore.RED}❌ 策略池加载失败: {e}")
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到策略池文件: {pool_path}")

    def _parse_tags(self, tag_str):
        """解析标签中的核心信息：热度、主力、题材"""
        if not isinstance(tag_str, str): return 999, ""

        # 1. 提取热度 Rank
        hot_match = re.search(r'🔥Top(\d+)', tag_str)
        hot_rank = int(hot_match.group(1)) if hot_match else 999

        # 2. 提取主力标识
        icons = []
        if '🏢' in tag_str: icons.append(f"{Fore.YELLOW}🏢机构{Fore.RESET}")
        if '🐉' in tag_str and '玄学' not in tag_str: icons.append(f"{Fore.CYAN}🐉游资{Fore.RESET}")

        # 3. 提取核心概念 (去除干扰项)
        # 简单处理：取第一个被/分隔的词，通常是核心概念
        concept = tag_str.split('/')[0] if tag_str else ""
        if 'Top' in concept or '竞价' in concept: concept = ""  # 过滤掉非概念词

        extra_info = " ".join(icons)
        return hot_rank, extra_info

    def _format_amt(self, amt):
        """金额格式化"""
        if amt > 100000000:
            return f"{Fore.RED}{amt / 100000000:.1f}亿{Fore.RESET}"
        elif amt > 10000000:
            return f"{Fore.YELLOW}{int(amt / 10000)}万{Fore.RESET}"
        else:
            return f"{int(amt / 10000)}万"

    def run(self):
        print(f"{Fore.CYAN}🦅 竞价监控启动 (V3.5 Smart Auction)... 按 Ctrl+C 退出")
        while True:
            try:
                self._scan_once()
                time.sleep(3)  # 竞价期间刷新频率
            except KeyboardInterrupt:
                print("\n监控结束")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)

    def _scan_once(self):
        # 1. 获取实时数据
        codes = list(self.strategy_pool.keys())
        if not codes: return

        # 分批获取，避免URL过长
        realtime_data = {}
        batch_size = 80
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            data = self.realtime_api.get_realtime_data(batch)
            realtime_data.update(data)

        # 2. 分析与排序
        results = []
        for code, row in realtime_data.items():
            pool_info = self.strategy_pool.get(code, {})
            name = row['name']

            # --- 核心指标计算 ---
            # 昨收价 (优先用策略池里的price，因为实时接口的pre_close有时不准)
            pre_close = float(pool_info.get('price', row['pre_close']))
            price = float(row['price'])

            if price <= 0 or pre_close <= 0: continue

            auc_pct = (price - pre_close) / pre_close * 100
            auc_amt = float(row['amount'])

            # 昨成交额 (从策略池获取，用于算量比)
            yest_amt = float(pool_info.get('amount', 0))
            ratio = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0

            # 昨涨幅 (用于判断弱转强前提)
            yest_pct = float(pool_info.get('pct', 0))

            # --- 智能分析 (调用策略库) ---
            # 构造 context 传入 analyze
            ctx = {'yest_pct': yest_pct, 'auc_amt': auc_amt, 'yest_amt': yest_amt}
            decision, color_code = self.analyzer.analyze(auc_pct, ratio, ctx)

            # --- 标签解析 ---
            tag_str = str(pool_info.get('tag', ''))
            hot_rank, smart_money_str = self._parse_tags(tag_str)

            # --- 排序打分 (Score) ---
            # 基础分: 竞价金额
            score = auc_amt

            # 加分项 1: 核按钮反转 (最高优先级)
            is_nuclear = '核反转' in decision
            if is_nuclear: score += 100_000_000_000

            # 加分项 2: 持仓 (关注优先级)
            is_holding = code in self.holdings
            if is_holding: score += 50_000_000_000

            # 加分项 3: "有身份"的弱转强 (弱转强 + 热度/主力)
            is_w2s = '弱转强' in decision
            is_top_hot = hot_rank <= 50
            has_smart_money = '🏢' in smart_money_str or '🐉' in smart_money_str

            if is_w2s:
                if is_top_hot or has_smart_money:
                    score += 10_000_000_000  # 黄金级机会
                else:
                    score += 1_000_000_000  # 普通机会

            # --- 组装结果 ---
            # 名称显示处理
            name_display = name
            if is_holding:
                name_display = f"{Back.BLUE}{Fore.WHITE}[持]{name}{Style.RESET_ALL}"
            elif is_top_hot:
                name_display = f"{Fore.RED}🔥{name}{Fore.RESET}"  # Top50 加火

            # 状态显示
            status_str = f"{color_code}{decision}{Style.RESET_ALL}"

            results.append({
                'code': code,
                'name_display': name_display,
                'hot_rank': hot_rank,
                'hot_str': f"Top{hot_rank}" if hot_rank < 200 else "-",
                'auc_pct': auc_pct,
                'auc_amt': auc_amt,
                'auc_amt_str': self._format_amt(auc_amt),
                'status': status_str,
                'smart_money': smart_money_str,
                'score': score
            })

        # 3. 排序与输出
        results.sort(key=lambda x: x['score'], reverse=True)

        # 清屏并打印
        os.system('cls' if os.name == 'nt' else 'clear')
        print(
            f"\n🚀 竞价监控 V3.5 | {time.strftime('%H:%M:%S')} | 标的: {len(results)} | 重点: {len([r for r in results if r['score'] > 1e9])}")
        print("=" * 110)
        print(f"{'代码':<8}{'名称':<14}{'热度':<8}{'竞价%':<10}{'金额':<12}{'状态/决策':<16}{'主力/题材'}")
        print("-" * 110)

        for r in results[:40]:  # 只显示前40，避免刷屏太快
            # 过滤掉金额太小且没戏的 (金额<500万 且 非持仓 且 非弱转强 且 非Top50)
            if r['auc_amt'] < 5000000 and "[持]" not in r['name_display'] and r['hot_rank'] > 50 and "弱转强" not in r[
                'status'] and "核反转" not in r['status']:
                continue

            print(f"{r['code']:<8}{r['name_display']:<23}{r['hot_str']:<10}"
                  f"{self._color_pct(r['auc_pct']):<14}{r['auc_amt_str']:<14}"
                  f"{r['status']:<25}{r['smart_money']}")
        print("=" * 110)

    def _color_pct(self, pct):
        if pct > 0:
            return f"{Fore.RED}+{pct:.2f}%{Fore.RESET}"
        elif pct < 0:
            return f"{Fore.GREEN}{pct:.2f}%{Fore.RESET}"
        else:
            return f"{pct:.2f}%"


if __name__ == "__main__":
    app = AuctionApp()
    app.run()