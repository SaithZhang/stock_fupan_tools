# ==============================================================================
# 📺 竞价监控 (src/monitors/call_auction_screener.py)
# Version: 3.1 (Hotfix)
# 修复：适配 V3 版数据接口字段 (trade -> price)
# ==============================================================================

import os
import sys
import time
import pandas as pd
from colorama import init, Fore, Style

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
        self.target_codes = set()

    def load_resources(self):
        """加载昨晚复盘结果 + 持仓"""
        print(f"{Fore.CYAN}📥 正在加载监控标的...")

        # 1. 持仓
        if os.path.exists(Config.HOLDINGS_PATH):
            raw = TextUtils.load_text_list(Config.HOLDINGS_PATH)
            for c in raw:
                sina_c = TextUtils.format_sina_code(c)
                self.holdings.add(sina_c)
                self.target_codes.add(sina_c)

        # 2. 策略池
        pool_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, dtype={'code': str})
                for _, row in df.iterrows():
                    sina_c = TextUtils.format_sina_code(str(row['code']).zfill(6))
                    self.strategy_pool[sina_c] = {
                        'name': str(row.get('name', '')),
                        'tag': str(row.get('tag', '')),
                        'yest_pct': float(row.get('today_pct', 0)),
                        'yest_amt': float(row.get('amount', 0))
                    }
                    self.target_codes.add(sina_c)
            except Exception as e:
                print(f"{Fore.RED}❌ 策略池读取失败: {e}")
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到策略池，仅监控持仓")

        print(f"✅ 监控构建: 持仓 {len(self.holdings)} | 策略池 {len(self.strategy_pool)}")

    def _format_amt(self, amt):
        if amt == 0: return "-"
        return f"{amt / 1_0000_0000:.1f}亿" if amt > 1_0000_0000 else f"{int(amt / 10000)}万"

    def run(self):
        self.load_resources()
        if not self.target_codes: return

        print(f"\n{Fore.YELLOW}🚀 获取竞价数据 (腾讯源)...")
        start_time = time.time()

        # 调用数据接口
        df = TencentRealtime.fetch_quotes(list(self.target_codes))
        if df.empty:
            print(f"{Fore.RED}❌ 数据获取失败")
            return

        results = []
        for _, row in df.iterrows():
            code = row['sina_code']
            pool_item = self.strategy_pool.get(code, {'name': '未知', 'tag': '', 'yest_pct': 0, 'yest_amt': 0})

            # --- 调用策略层 ---
            board_cnt = AuctionStrategy.get_board_count(pool_item['tag'])
            clean_tag = AuctionStrategy.clean_tag(pool_item['tag'], board_cnt)
            status_str = AuctionStrategy.analyze_status(
                pool_item['yest_pct'], row['pct'], pool_item['tag'], code in self.holdings
            )
            is_huge_vol = AuctionStrategy.check_volume(pool_item['yest_amt'], row['amount'])

            # --- 样式处理 ---
            name_display = pool_item['name']
            if code in self.holdings:
                name_display = f"{Fore.MAGENTA}{name_display}{Style.RESET_ALL}"

            board_str = f"{Fore.YELLOW}{board_cnt}板{Style.RESET_ALL}" if board_cnt >= 2 else ""
            auc_color = Fore.RED if row['pct'] > 0 else (Fore.GREEN if row['pct'] < 0 else Fore.WHITE)
            yest_color = Fore.RED if pool_item['yest_pct'] > 0 else (
                Fore.GREEN if pool_item['yest_pct'] < 0 else Fore.WHITE)
            amt_color = Fore.RED if is_huge_vol else Fore.WHITE

            results.append({
                'code': code[-6:],
                'name': name_display,
                'auc_pct': row['pct'],
                'auc_color': auc_color,
                'yest_pct': pool_item['yest_pct'],
                'yest_color': yest_color,
                'board': board_str,
                # 修复点: 这里的 key 必须和 src/data/realtime.py 返回的 dict 一致
                'price': row['price'],
                'auc_amt_str': self._format_amt(row['amount']),
                'amt_color': amt_color,
                'yest_amt_str': self._format_amt(pool_item['yest_amt']),
                'mv_str': f"{row['mv_yi']:.1f}亿",
                'status': status_str,
                'tag': clean_tag,
                'sort_key': (code in self.holdings, board_cnt, row['pct'])
            })

        # 排序
        results.sort(key=lambda x: x['sort_key'], reverse=True)

        # 打印
        print("-" * 125)
        print(
            f"{'代码':<8}{'名称':<12}{'竞价%':<10}{'昨幅%':<10}{'连板':<8}{'现价':<8}{'竞价金额':<10}{'昨额':<10}{'市值':<10}{'AI决策/标签'}")
        print("-" * 125)

        for r in results:
            print(
                f"{r['code']:<8}"
                f"{r['name']:<22}"
                f"{r['auc_color']}{r['auc_pct']:>6.2f}%{Style.RESET_ALL}   "
                f"{r['yest_color']}{r['yest_pct']:>6.2f}%{Style.RESET_ALL}   "
                f"{r['board']:<16}"
                f"{r['price']:<8.2f}"
                f"{r['amt_color']}{r['auc_amt_str']:<10}{Style.RESET_ALL}"
                f"{r['yest_amt_str']:<10}"
                f"{r['mv_str']:<10}"
                f"{r['status']} {Fore.CYAN}{r['tag']}{Style.RESET_ALL}"
            )

        print("-" * 125)
        print(f"⏱️ 耗时: {time.time() - start_time:.2f}s | 来源: 腾讯财经HTTP | 架构: V3.1 (Stable)")


if __name__ == "__main__":
    try:
        AuctionApp().run()
    except KeyboardInterrupt:
        pass