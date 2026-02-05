# ==============================================================================
# 🔭 盘中监控雷达 (src/monitors/intraday_monitor.py)
# Version: 3.1 (Market Sentiment + Multi-thread Speedup)
# 核心功能：腾讯源实时监控 + 东方财富板块 + 策略池联动 + 异动刷新
# ==============================================================================

import time
import os
import sys
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    # ⬇️ 引入新封装的 EastMoneyBlock
    from src.data.realtime import TencentRealtime, EastMoneyBlock
    from src.strategies.intraday import IntradayStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


# --- 辅助类：市场数据获取 (东方财富板块 + 腾讯指数) ---
class MarketDataHelper:
    @staticmethod
    def get_sectors():
        """
        获取东方财富领涨行业板块 (Top 5)
        URL: EastMoney Push API
        """
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1, "pz": 6, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90 t:2 f:!50",
                "fields": "f14,f3"  # f14:名称, f3:涨幅
            }
            res = requests.get(url, params=params, timeout=1.5)
            data = res.json()
            if data and data.get('data'):
                return data['data']['diff']  # list of dict
        except Exception:
            return []
        return []

    @staticmethod
    def get_indices_codes():
        """返回核心指数代码 (腾讯接口格式)"""
        # 上证指数, 深证成指, 创业板指, 科创50, 沪深300
        return ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300']


class IntradayMonitor:
    def __init__(self):
        self.strategy_pool = {}  # {sina_code: {tag:..., name:...}}
        self.holdings = set()
        self.target_codes = set()

        # 状态快照 {sina_code: last_price} 用于计算异动
        self.price_snapshot = {}

        # 线程池 (用于并发请求)
        self.executor = ThreadPoolExecutor(max_workers=3)

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
        """格式化金额显示"""
        if amt > 1_0000_0000: return f"{amt / 1_0000_0000:.1f}亿"
        return f"{int(amt / 10000)}万"

    # ⬇️ 更新 fetch_all_data 方法
    def fetch_all_data(self):
        """并发获取：个股数据、大盘指数、板块数据"""
        # 定义大盘指数代码
        indices_codes = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300']

        tasks = {
            'stocks': self.executor.submit(TencentRealtime.fetch_quotes, list(self.target_codes)),
            'indices': self.executor.submit(TencentRealtime.fetch_quotes, indices_codes),
            # ⬇️ 直接调用新类的方法
            'sectors': self.executor.submit(EastMoneyBlock.fetch_all_sectors)
        }

        results = {}
        for key, future in tasks.items():
            try:
                results[key] = future.result()
            except Exception:
                results[key] = None
        return results

    def print_dashboard(self, indices_df, sectors_list, now_str):
        """打印顶部仪表盘 (大盘 + 板块)"""
        os.system('cls' if os.name == 'nt' else 'clear')

        # --- Header ---
        print(
            f"{Back.BLUE}{Fore.WHITE} 🔭 盘中监控雷达 (V3.1) {Style.RESET_ALL} | Time: {now_str} | 标的: {len(self.target_codes)}")

        # --- Line 1: Indices (大盘) ---
        if indices_df is not None and not indices_df.empty:
            idx_str = ""
            total_amt = 0
            for _, row in indices_df.iterrows():
                # 简写名称
                name_map = {'上证指数': '上证', '深证成指': '深证', '创业板指': '创业', '科创50': '科创',
                            '沪深300': 'HS300'}
                name = name_map.get(row['name'], row['name'])

                # 颜色
                color = Fore.RED if row['pct'] > 0 else (Fore.GREEN if row['pct'] < 0 else Fore.WHITE)
                idx_str += f"{name}:{color}{row['pct']:+.2f}%{Style.RESET_ALL}  "

                # 累加成交额 (粗略计算全市场热度)
                if row['amount'] > 0:
                    total_amt += row['amount']

            # 显示总金额 (近似)
            # 注意：指数的amount通常单位不统一，需根据TencentRealtime实际返回调整。通常sh000001+sz399001包含大部分
            print(f"📊 {idx_str}")
        else:
            print("📊 指数数据加载中...")
        # --- Line 2 & 3: Sectors (板块情绪) ---
        if sectors_list:
            # 这里的字段名已经统一为 'pct' 和 'name' 了，修改一下取值方式
            sectors_list.sort(key=lambda x: x['pct'], reverse=True)

            # 领涨 (前5)
            top_gainers = sectors_list[:5]
            up_str = f"{Fore.RED}🔥 领涨: {Style.RESET_ALL}"
            for s in top_gainers:
                up_str += f"{s['name']} {Fore.RED}{s['pct']:+.1f}%{Style.RESET_ALL}  "

            # 领跌 (后5)
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
        """执行一次全量刷新"""
        if not self.target_codes: return

        # 1. 并发获取数据
        data_map = self.fetch_all_data()
        df_stocks = data_map.get('stocks')
        df_indices = data_map.get('indices')
        list_sectors = data_map.get('sectors')

        if df_stocks is None or df_stocks.empty: return

        now_str = datetime.now().strftime("%H:%M:%S")

        # 2. 先打印顶部仪表盘
        self.print_dashboard(df_indices, list_sectors, now_str)

        # 3. 处理个股逻辑
        display_items = []
        for _, row in df_stocks.iterrows():
            code = row['sina_code']
            pool_info = self.strategy_pool.get(code, {'name': row['name'], 'tag': '', 'limit_up_type': ''})

            # --- 策略判定 ---
            status_str, is_zt = IntradayStrategy.check_status(
                row['price'], row['limit_up'], row['limit_down'], row['pct']
            )

            # 动态异动
            last_p = self.price_snapshot.get(code, 0)
            dynamic_alert = IntradayStrategy.check_dynamic_alert(row['price'], last_p)
            self.price_snapshot[code] = row['price']

            final_signal = dynamic_alert if dynamic_alert else status_str

            # 补充信息
            extra_info = ""
            if pool_info['limit_up_type'] and "一字" in pool_info['limit_up_type']:
                extra_info = "[一字]"

            import re
            match = re.search(r'(\d+)板', pool_info['tag'])
            if match:
                extra_info += f" {match.group(1)}板"

            # 持仓标记
            is_holding = code in self.holdings

            # 样式处理
            name_show = pool_info['name']
            if is_holding:
                name_show = f"{Fore.MAGENTA}{name_show}{Style.RESET_ALL}"
                final_signal = f"{Fore.MAGENTA}[持]{Style.RESET_ALL} " + final_signal

            pct_color = IntradayStrategy.get_pct_color(row['pct'])
            vr_str = f"{row['vol_ratio']:.1f}"
            if row['vol_ratio'] > 2.0: vr_str = f"{Fore.RED}{vr_str}{Style.RESET_ALL}"

            # 排序权重: 持仓 > 涨停 > 涨幅绝对值
            sort_key = (is_holding, is_zt, abs(row['pct']))

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
                'tag': pool_info['tag'].replace(match.group(0) if match else "", "").strip(),
                'sort_key': sort_key
            })

        # 4. 排序与表格显示
        display_items.sort(key=lambda x: x['sort_key'], reverse=True)

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
        self.load_resources()
        print("\n🚀 极速监控启动 (Tencent+EastMoney)，按 Ctrl+C 退出...")
        try:
            while True:
                t_start = time.time()
                self.refresh()
                # 动态休眠：如果刷新太快(小于0.5s)，则补足时间，防止接口封禁；否则立即进行下一轮
                elapsed = time.time() - t_start
                sleep_time = max(2.5, 3.0 - elapsed)  # 保持约3秒一刷
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n👋 监控已停止")
            self.executor.shutdown(wait=False)


if __name__ == "__main__":
    IntradayMonitor().run_loop()