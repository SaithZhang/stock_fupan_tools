# ==============================================================================
# 🔭 盘中监控雷达 (src/monitors/intraday_monitor.py)
# Version: 3.4 (Ultimate Fix & Hot-Reload Edition)
# 核心功能：复用 manual_focus + 动态提取标签 + 修复持仓前缀 + 兼容量能字段
# ==============================================================================

import time
import os
import sys
import re
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
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
    from src.data.realtime import TencentRealtime, EastMoneyBlock
    from src.strategies.intraday import IntradayStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class MarketDataHelper:
    @staticmethod
    def get_sectors():
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1, "pz": 6, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90 t:2 f:!50",
                "fields": "f14,f3"
            }
            res = requests.get(url, params=params, timeout=1.5)
            data = res.json()
            if data and data.get('data'):
                return data['data']['diff']
        except Exception:
            return []
        return []

    @staticmethod
    def get_indices_codes():
        return ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300']


class IntradayMonitor:
    def __init__(self):
        self.strategy_pool = {}
        self.holdings = set()
        self.target_codes = set()
        self.manual_focus_pool = {}  # {sina_code: 提取的标签}
        self.price_snapshot = {}
        self.executor = ThreadPoolExecutor(max_workers=3)

        # 强制复用原有的 manual_focus.txt
        self.manual_focus_path = os.path.join(project_root, 'data', 'input', 'manual_focus.txt')

    def load_resources(self):
        # 热更新前清空原有池子
        self.manual_focus_pool.clear()
        self.holdings.clear()

        # 1. 加载持仓
        if os.path.exists(Config.HOLDINGS_PATH):
            raw = TextUtils.load_text_list(Config.HOLDINGS_PATH)
            for c in raw:
                sina_c = TextUtils.format_sina_code(c)
                self.holdings.add(sina_c)
                self.target_codes.add(sina_c)

        # 2. 加载策略池
        pool_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, dtype={'code': str})
                for _, row in df.iterrows():
                    sina_c = TextUtils.format_sina_code(str(row['code']).zfill(6))
                    tag = str(row.get('tag', ''))
                    tag = tag.replace("DDD", "").replace("1进2", "").replace("/", " ").strip()
                    self.strategy_pool[sina_c] = {
                        'name': str(row.get('name', '')),
                        'tag': tag[:15],
                        'limit_up_type': str(row.get('limit_up_type', ''))
                    }
                    self.target_codes.add(sina_c)
            except Exception:
                pass

        # 3. 🚀 智能加载 manual_focus.txt
        if os.path.exists(self.manual_focus_path):
            current_section_tag = "⭐重点关注"
            with open(self.manual_focus_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue

                    # 智能解析分组头，如 "# --- TACO核心 ---"
                    if line.startswith('#'):
                        if '---' in line:
                            clean_header = line.replace('#', '').replace('-', '').strip()
                            if clean_header:
                                current_section_tag = clean_header[:8]
                        continue

                    # 匹配行首的6位股票代码
                    match = re.search(r'^(\d{6})', line)
                    if match:
                        raw_code = match.group(1)
                        sina_c = TextUtils.format_sina_code(raw_code)

                        # 尝试提取行内括号里的特定备注
                        inline_match = re.search(r'\((.*?)\)|（(.*?)）', line)
                        if inline_match:
                            final_tag = inline_match.group(1) or inline_match.group(2)
                        else:
                            final_tag = current_section_tag

                        self.manual_focus_pool[sina_c] = final_tag
                        self.target_codes.add(sina_c)

    def _format_amt(self, amt):
        if amt > 1_0000_0000: return f"{amt / 1_0000_0000:.1f}亿"
        return f"{int(amt / 10000)}万"

    def fetch_all_data(self):
        tr = TencentRealtime()
        emb = EastMoneyBlock()
        indices_codes = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300']

        tasks = {
            'stocks': self.executor.submit(tr.get_batch_quotes, list(self.target_codes)),
            'indices': self.executor.submit(tr.get_batch_quotes, indices_codes),
            'sectors': self.executor.submit(emb.fetch_all_sectors)
        }

        results = {}
        for key, future in tasks.items():
            try:
                results[key] = future.result()
            except Exception:
                results[key] = None

        if results.get('stocks'):
            df = pd.DataFrame.from_dict(results['stocks'], orient='index')

            # --- 🚀 强力兼容量能字段 ---
            if 'turnover' not in df.columns: df['turnover'] = 0.0
            if 'vol_ratio' not in df.columns: df['vol_ratio'] = 0.0
            if 'amount' not in df.columns: df['amount'] = 0.0

            df['turnover'] = pd.to_numeric(df['turnover'], errors='coerce').fillna(0.0)
            df['vol_ratio'] = pd.to_numeric(df['vol_ratio'], errors='coerce').fillna(0.0)
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)

            df['sina_code'] = df.index
            results['stocks'] = df

        if results.get('indices'):
            results['indices'] = pd.DataFrame.from_dict(results['indices'], orient='index')

        return results

    def print_dashboard(self, indices_df, sectors_list, now_str):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(
            f"{Back.BLUE}{Fore.WHITE} 🔭 盘中监控雷达 (V3.4 最终修复版) {Style.RESET_ALL} | Time: {now_str} | 监控池: {len(self.target_codes)}")

        if indices_df is not None and not indices_df.empty:
            idx_str = ""
            for _, row in indices_df.iterrows():
                name_map = {'上证指数': '上证', '深证成指': '深证', '创业板指': '创业', '科创50': '科创',
                            '沪深300': 'HS300'}
                name = name_map.get(row['name'], row['name'])
                color = Fore.RED if row['pct'] > 0 else (Fore.GREEN if row['pct'] < 0 else Fore.WHITE)
                idx_str += f"{name}:{color}{row['pct']:+.2f}%{Style.RESET_ALL}  "
            print(f"📊 {idx_str}")
        else:
            print("📊 指数数据加载中...")

        if sectors_list:
            sectors_list.sort(key=lambda x: x['pct'], reverse=True)
            top_gainers = sectors_list[:5]
            up_str = f"{Fore.RED}🔥 领涨: {Style.RESET_ALL}"
            for s in top_gainers:
                up_str += f"{s['name']} {Fore.RED}{s['pct']:+.1f}%{Style.RESET_ALL}  "
            top_losers = sectors_list[-5:]
            top_losers.reverse()
            down_str = f"{Fore.GREEN}❄️ 领跌: {Style.RESET_ALL}"
            for s in top_losers:
                down_str += f"{s['name']} {Fore.GREEN}{s['pct']:+.1f}%{Style.RESET_ALL}  "
            print(up_str)
            print(down_str)
        else:
            print("⚠️ 板块数据加载失败")
        print("-" * 115)

    def refresh(self):
        # 🚀 每次刷新都重载，实现热更新
        self.load_resources()

        if not self.target_codes: return

        data_map = self.fetch_all_data()
        df_stocks = data_map.get('stocks')
        df_indices = data_map.get('indices')
        list_sectors = data_map.get('sectors')

        if df_stocks is None or df_stocks.empty: return

        now_str = datetime.now().strftime("%H:%M:%S")
        self.print_dashboard(df_indices, list_sectors, now_str)

        display_items = []
        for _, row in df_stocks.iterrows():
            # 🚀 完美解决变量作用域和前缀匹配 Bug
            code = str(row['sina_code'])
            pure_code = code

            prefix_code = pure_code
            if pure_code.startswith('6'):
                prefix_code = f"sh{pure_code}"
            elif pure_code.startswith(('0', '3')):
                prefix_code = f"sz{pure_code}"
            elif pure_code.startswith(('4', '8')):
                prefix_code = f"bj{pure_code}"

            # 1. 匹配自定义关注池
            manual_label = self.manual_focus_pool.get(pure_code) or self.manual_focus_pool.get(prefix_code)
            is_focus = manual_label is not None

            # 2. 匹配策略池
            pool_info = self.strategy_pool.get(pure_code) or self.strategy_pool.get(prefix_code)
            if not pool_info:
                pool_info = {'name': row['name'], 'tag': manual_label if manual_label else '', 'limit_up_type': ''}

            # 3. 匹配持仓 (核心防错漏)
            is_holding = (pure_code in self.holdings) or (prefix_code in self.holdings)

            # 4. 状态与异动计算
            status_str, is_zt = IntradayStrategy.check_status(
                row['price'], row['limit_up'], row['limit_down'], row['pct']
            )

            last_p = self.price_snapshot.get(code, 0)
            dynamic_alert = IntradayStrategy.check_dynamic_alert(row['price'], last_p)
            self.price_snapshot[code] = row['price']

            final_signal = dynamic_alert if dynamic_alert else status_str
            extra_info = "[一字]" if pool_info['limit_up_type'] and "一字" in pool_info['limit_up_type'] else ""

            match = re.search(r'(\d+)板', pool_info['tag'])
            if match:
                extra_info += f" {match.group(1)}板"

            name_show = pool_info['name']

            # 🚀 视觉优先级：自定义关注 > 持仓
            if is_focus:
                name_show = f"{Back.MAGENTA}{Fore.WHITE}{name_show}{Style.RESET_ALL}"
                final_signal = f"{Back.MAGENTA}{Fore.WHITE}[{manual_label}]{Style.RESET_ALL} " + final_signal
            elif is_holding:
                name_show = f"{Fore.MAGENTA}{name_show}{Style.RESET_ALL}"
                final_signal = f"{Fore.MAGENTA}[持仓]{Style.RESET_ALL} " + final_signal

            pct_color = IntradayStrategy.get_pct_color(row['pct'])

            # 量比高亮处理
            vr_str = f"{row['vol_ratio']:.1f}"
            if row['vol_ratio'] > 2.0: vr_str = f"{Fore.RED}{vr_str}{Style.RESET_ALL}"

            # 🚀 排序权重优化：关注的标的强制置顶
            sort_key = (is_focus, is_holding, is_zt, abs(row['pct']))

            raw_tag = pool_info['tag']
            if match: raw_tag = raw_tag.replace(match.group(0), "")
            clean_tag = raw_tag.strip()

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
                'tag': clean_tag,
                'sort_key': sort_key
            })

        # 执行排序
        display_items.sort(key=lambda x: x['sort_key'], reverse=True)

        # 打印表头
        print(
            f"{'代码':<8}{'名称':<14}{'涨幅':<10}{'现价':<8}{'换手%':<8}{'量比':<8}{'成交额':<10}{'异动/状态':<14}{'策略标签'}")
        print("-" * 115)

        max_rows = 500
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
        print("\n🚀 极速监控启动 (Tencent+EastMoney)，按 Ctrl+C 退出...")
        try:
            while True:
                t_start = time.time()
                self.refresh()
                elapsed = time.time() - t_start
                sleep_time = max(2.5, 3.0 - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n👋 监控已停止")
            self.executor.shutdown(wait=False)


if __name__ == "__main__":
    IntradayMonitor().run_loop()