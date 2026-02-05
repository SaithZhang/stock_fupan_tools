# ==============================================================================
# 📺 竞价监控 (src/monitors/call_auction_screener.py)
# Version: 3.3 (Nuclear Reversal Highlight)
# 核心功能：竞价排序 + 弱转强(核反转)紫色高亮预警
# ==============================================================================

import os
import sys
import time
import pandas as pd
import glob
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
        self.target_codes = set()
        self.tc_api = TencentRealtime()

    def load_pool(self):
        """加载昨晚复盘生成的策略池"""
        print(f"{Fore.CYAN}📥 正在加载监控标的...", end="")

        # 1. 加载持仓
        try:
            self.holdings = set(TextUtils.load_text_list(Config.HOLDINGS_PATH))
        except:
            self.holdings = set()

        # 2. 加载最新策略池
        pattern = os.path.join(Config.OUTPUT_DIR, 'strategy_pool_v2_*.csv')
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

        if not files:
            print(f" {Fore.RED}未找到策略池文件！")
            return

        try:
            df = pd.read_csv(files[0], dtype={'code': str, 'sina_code': str})
            self.strategy_pool = {}
            for _, row in df.iterrows():
                # 兼容不同列名
                code = str(row.get('sina_code', '')).strip()
                if not code or code == 'nan':
                    raw_code = str(row['code']).zfill(6)
                    code = f"sh{raw_code}" if raw_code.startswith('6') else f"sz{raw_code}"

                self.strategy_pool[code] = {
                    'name': row['name'],
                    'tag': str(row['tag']),
                    'yest_pct': float(row['today_pct']),  # 昨天的涨跌幅
                    'yest_amt': float(row['amount']),  # 昨天的成交额
                    'board_cnt': str(row.get('limit_up_type', ''))  # 连板数/类型
                }

            self.target_codes = list(set(self.strategy_pool.keys()) | self.holdings)
            # 过滤非法代码
            self.target_codes = [c for c in self.target_codes if c.startswith('sz') or c.startswith('sh')]

            print(f" ✅ 监控构建: 持仓 {len(self.holdings)} | 策略池 {len(self.strategy_pool)}")

        except Exception as e:
            print(f" {Fore.RED}加载失败: {e}")

    def _format_amt(self, amt):
        if amt > 1_0000_0000: return f"{amt / 1_0000_0000:.1f}亿"
        return f"{int(amt / 10000)}万"

    def run(self):
        self.load_pool()
        print(f"\n🚀 获取竞价数据 (腾讯源)...")

        # 获取实时数据
        realtime = self.tc_api.get_batch_quotes(self.target_codes)

        results = []
        for code, row in realtime.items():
            pool_item = self.strategy_pool.get(code, {})

            # --- 基础数据 ---
            name = row['name']
            if not name or name == '未知': name = pool_item.get('name', '未知')

            # 竞价涨幅
            auc_pct = row['pct']  # 9:25前 pct 即为竞价涨幅
            auc_amt = row['amount']  # 竞价成交额

            # 昨收涨幅 (用于判断核按钮反转)
            yest_pct = pool_item.get('yest_pct', 0.0)

            # 连板高度
            board_cnt = pool_item.get('board_cnt', '')
            if '板' not in board_cnt: board_cnt = ''

            # --- 🎨 核心打标逻辑 ---

            tags = []

            # 1. 👑 核按钮反转 (弱转强) 高亮逻辑
            is_nuclear_reversal = False
            if yest_pct < -9.0 and auc_pct > 0.0:
                tags.append(f"{Back.MAGENTA}{Fore.WHITE}👑核反转{Style.RESET_ALL}")
                is_nuclear_reversal = True

            # 2. 竞价爆量
            # 简单算法：竞价金额 > 昨日全天金额 * 10% (视为超预期)
            # 或者绝对金额 > 3000万
            yest_total_amt = pool_item.get('yest_amt', 1)
            ratio = auc_amt / yest_total_amt if yest_total_amt > 0 else 0

            if auc_amt > 1_0000_0000:
                tags.append(f"{Fore.RED}💰竞价过亿{Style.RESET_ALL}")
            elif ratio > 0.1:
                tags.append(f"{Fore.RED}🔥超预期{Style.RESET_ALL}")
            elif auc_amt > 3000_0000:
                tags.append("⚡竞价达标")

            # 3. 策略标签
            orig_tag = pool_item.get('tag', '').replace('nan', '')
            # 简化显示
            clean_tag = orig_tag.replace("DDD", "").replace("1进2", "").replace("[换手板]", "")
            if len(clean_tag) > 15: clean_tag = clean_tag[:15] + "..."

            # 组合
            display_tag = " ".join(tags) + " " + clean_tag

            # --- 颜色处理 ---
            name_color = Fore.WHITE
            if code in self.holdings: name_color = Fore.CYAN + "[持]"
            if is_nuclear_reversal: name_color = Fore.MAGENTA + "★"  # 名字前加星

            auc_color = Fore.RED if auc_pct > 0 else (Fore.GREEN if auc_pct < 0 else Fore.WHITE)

            yest_color = Fore.GREEN if yest_pct < 0 else Fore.RED

            # 构造行数据
            results.append({
                'code': code[2:],
                'name': name,
                'name_display': f"{name_color}{name:<8}{Style.RESET_ALL}",
                'auc_pct': auc_pct,
                'auc_color': auc_color,
                'yest_pct': yest_pct,
                'yest_color': yest_color,
                'board': board_cnt,
                'price': row['price'],
                'auc_amt_str': self._format_amt(auc_amt),
                'yest_amt_str': self._format_amt(yest_total_amt),
                'tag': display_tag,
                # 排序键：核反转 > 持仓 > 竞价金额
                'sort_key': (is_nuclear_reversal, code in self.holdings, auc_amt)
            })

        # 排序
        results.sort(key=lambda x: x['sort_key'], reverse=True)

        # 打印表头
        print("-" * 130)
        print(
            f"{'代码':<8}{'名称':<14}{'竞价%':<10}{'昨幅%':<10}{'连板':<8}{'现价':<8}{'竞价金额':<10}{'昨额':<10}{'AI决策/标签'}")
        print("-" * 130)

        for r in results:
            # 过滤掉没量的垃圾股 (除非是持仓或核反转)
            if r['auc_amt_str'] == '0万' and "[持]" not in r['name_display'] and "核反转" not in r['tag']:
                continue

            print(
                f"{r['code']:<8}"
                f"{r['name_display']:<22}"
                f"{r['auc_color']}{r['auc_pct']:>6.2f}%{Style.RESET_ALL}   "
                f"{r['yest_color']}{r['yest_pct']:>6.2f}%{Style.RESET_ALL}   "
                f"{r['board']:<8}"
                f"{r['price']:<8.2f}"
                f"{Fore.YELLOW}{r['auc_amt_str']:<10}{Style.RESET_ALL}"
                f"{r['yest_amt_str']:<10}"
                f"{r['tag']}"
            )


if __name__ == "__main__":
    app = AuctionApp()
    app.run()