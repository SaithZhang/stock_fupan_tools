# ==============================================================================
# 🔭 盘中监控雷达 (src/monitors/intraday_monitor.py)
# Version: 3.0 (Modular Refactor)
# 核心功能：腾讯源实时监控 + 策略池联动 + 异动刷新
# ==============================================================================

import time
import os
import sys
import pandas as pd
from datetime import datetime
from colorama import init, Fore, Style, Back

# --- 环境初始化 ---
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
    from src.strategies.intraday import IntradayStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class IntradayMonitor:
    def __init__(self):
        self.strategy_pool = {}  # {sina_code: {tag:..., name:...}}
        self.holdings = set()
        self.target_codes = set()

        # 状态快照 {sina_code: last_price} 用于计算异动
        self.price_snapshot = {}

    def load_resources(self):
        """加载基础数据"""
        print(f"{Fore.CYAN}📥 正在构建监控池...", end="")

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

                    # 简化标签显示
                    tag = str(row.get('tag', ''))
                    tag = tag.replace("DDD", "").replace("1进2", "").replace("/", " ").strip()

                    self.strategy_pool[sina_c] = {
                        'name': str(row.get('name', '')),
                        'tag': tag[:15],
                        'limit_days': row.get('limit_days', 0),
                        'limit_up_type': str(row.get('limit_up_type', ''))
                    }
                    self.target_codes.add(sina_c)
            except Exception:
                pass

        print(f" 完成 | 监控标的: {len(self.target_codes)}")

    def _format_amt(self, amt):
        if amt > 1_0000_0000: return f"{amt / 1_0000_0000:.1f}亿"
        return f"{int(amt / 10000)}万"

    def refresh(self):
        """执行一次刷新"""
        if not self.target_codes: return

        # 1. 获取数据
        df = TencentRealtime.fetch_quotes(list(self.target_codes))
        if df.empty: return

        display_items = []
        now_str = datetime.now().strftime("%H:%M:%S")

        for _, row in df.iterrows():
            code = row['sina_code']
            pool_info = self.strategy_pool.get(code, {'name': row['name'], 'tag': '', 'limit_up_type': ''})

            # --- 策略判定 ---
            # A. 涨跌停
            status_str, is_zt = IntradayStrategy.check_status(
                row['price'], row['limit_up'], row['limit_down'], row['pct']
            )

            # B. 动态异动 (对比上一轮)
            last_p = self.price_snapshot.get(code, 0)
            dynamic_alert = IntradayStrategy.check_dynamic_alert(row['price'], last_p)
            self.price_snapshot[code] = row['price']  # 更新快照

            # 优先显示异动，其次显示状态
            final_signal = dynamic_alert if dynamic_alert else status_str

            # C. 补充连板/一字信息 (来自昨晚复盘)
            extra_info = ""
            if pool_info['limit_up_type'] and "一字" in pool_info['limit_up_type']:
                extra_info = "[一字]"

            # 连板数 (从tag提取)
            import re
            match = re.search(r'(\d+)板', pool_info['tag'])
            if match:
                extra_info += f" {match.group(1)}板"

            # --- 过滤逻辑 (可选) ---
            # 如果不是持仓，且波动很小，不显示 (防刷屏)
            is_holding = code in self.holdings
            is_active = abs(row['pct']) > 3.0 or final_signal or is_zt or (row['vol_ratio'] > 2.0)

            # if not is_holding and not is_active: continue

            # --- 样式 ---
            name_show = pool_info['name']
            if is_holding:
                name_show = f"{Fore.MAGENTA}{name_show}{Style.RESET_ALL}"
                final_signal = f"{Fore.MAGENTA}[持]{Style.RESET_ALL} " + final_signal

            pct_color = IntradayStrategy.get_pct_color(row['pct'])
            vr_str = f"{row['vol_ratio']:.1f}"
            if row['vol_ratio'] > 2.0: vr_str = f"{Fore.RED}{vr_str}{Style.RESET_ALL}"

            display_items.append({
                'code': code[-6:],
                'name': name_show,
                'pct': row['pct'],
                'pct_str': f"{pct_color}{row['pct']:>6.2f}%{Style.RESET_ALL}",
                'price': row['price'],
                'turnover': row['turnover'],
                'vr_str': vr_str,
                'amt_str': self._format_amt(row['amount']),
                'signal': final_signal,
                'extra': extra_info,
                'tag': pool_info['tag'].replace(match.group(0) if match else "", "").strip(),  # 去除板数免重复
                'sort_key': (is_holding, is_zt, row['pct'])  # 排序优先级
            })

        # 排序
        display_items.sort(key=lambda x: x['sort_key'], reverse=True)

        # 清屏并打印
        os.system('cls' if os.name == 'nt' else 'clear')

        print(
            f"{Back.BLUE}{Fore.WHITE} 🔭 盘中监控中心 (V3.0) {Style.RESET_ALL} | Time: {now_str} | 标的: {len(self.target_codes)}")
        print("-" * 115)
        print(
            f"{'代码':<8}{'名称':<14}{'涨幅':<10}{'现价':<8}{'换手%':<8}{'量比':<8}{'成交额':<10}{'异动/状态':<14}{'策略标签'}")
        print("-" * 115)

        max_rows = 40  # 每屏最多显示多少行
        for item in display_items[:max_rows]:
            print(
                f"{item['code']:<8}"
                f"{item['name']:<24}"
                f"{item['pct_str']:<18}"
                f"{item['price']:<8.2f}"
                f"{item['turnover']:<8.1f}"
                f"{item['vr_str']:<17}"
                f"{item['amt_str']:<10}"
                f"{item['signal']:<22}"
                f"{Fore.YELLOW}{item['extra']:<10}{Style.RESET_ALL} {Fore.CYAN}{item['tag']}{Style.RESET_ALL}"
            )

        if len(display_items) > max_rows:
            print(f"\n... 还有 {len(display_items) - max_rows} 只低波动标的已隐藏 ...")

    def run_loop(self):
        self.load_resources()
        print("\n🚀 监控启动，按 Ctrl+C 退出...")
        try:
            while True:
                self.refresh()
                time.sleep(3)  # 3秒刷新一次
        except KeyboardInterrupt:
            print("\n👋 监控已停止")


if __name__ == "__main__":
    IntradayMonitor().run_loop()