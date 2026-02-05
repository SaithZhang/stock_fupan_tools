# ==============================================================================
# 🔭 盘中做T雷达 V2 (src/monitors/intraday_monitor_v2.py)
# Version: 4.0 (Tushare V3 Ultimate)
# 核心功能：基于 rt_k 和 rt_min 的日内回转(T+0)辅助系统
# 狼大心法：均价线下方低吸，急拉乖离率过大高抛，关注5日线支撑
# ==============================================================================

import time
import os
import sys
import pandas as pd
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
    from src.data.tushare_manager import TushareManager
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class IntradayMonitorV2:
    def __init__(self):
        self.ts_manager = TushareManager()
        self.holdings = set()  # 你的持仓
        self.target_codes = set()  # 你的策略池
        self.strategy_map = {}  # {code: {name:..., tag:...}}

        # 缓存上一次的价格，用于计算短时急拉/急跌
        self.last_prices = {}

    def load_resources(self):
        """加载持仓和策略池"""
        print(f"{Fore.CYAN}📥 [V2] 正在加载做T标的...", end="")

        # 1. 加载持仓 (这是做T的核心对象)
        if os.path.exists(Config.HOLDINGS_PATH):
            raw = TextUtils.load_text_list(Config.HOLDINGS_PATH)
            for c in raw:
                # 兼容格式，只取纯数字代码用于匹配，但Tushare需要后缀
                # 这里我们假设 strategy_pool.csv 里有完整的 ts_code
                # 或者我们需要一个映射。简单起见，我们暂存纯代码
                pure_code = c.split('.')[0]
                self.holdings.add(pure_code)

        # 2. 加载策略池
        pool_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, dtype={'code': str})
                for _, row in df.iterrows():
                    pure_code = str(row['code']).zfill(6)
                    # 尝试恢复 Tushare 格式 (粗略判断)
                    suffix = ".SH" if pure_code.startswith('6') else (
                        ".BJ" if pure_code.startswith(('8', '4')) else ".SZ")
                    ts_code = f"{pure_code}{suffix}"

                    self.target_codes.add(ts_code)
                    self.strategy_map[pure_code] = {
                        'name': row.get('name', '未知'),
                        'tag': str(row.get('tag', ''))[:10]
                    }
            except Exception:
                pass

        print(f" 完成 | 监控标的: {len(self.target_codes)}")

    def calculate_t_signal(self, row, vwap):
        """
        计算做T信号 (狼大策略)
        :param row: rt_k 的一行数据
        :param vwap: 盘中均价
        """
        current_price = row['close']  # 在rt_k中，close即为最新价
        high = row['high']
        low = row['low']
        pre_close = row['pre_close']

        signal = ""
        color = Fore.WHITE

        # 1. 乖离率计算 (当前价格偏离均价的程度)
        bias = (current_price - vwap) / vwap * 100

        # 2. 信号判定

        # --- 卖点逻辑 (High Throw) ---
        # 如果价格急拉，且偏离均价超过 2%~3%，通常是日内高抛点
        if bias > 2.5:
            signal = "⚠️高乖离(卖)"
            color = Fore.GREEN
        elif current_price == high and row['pct_chg'] < 9.5:
            # 未涨停但摸到最高价，可能有阻力
            signal = "🚫遇阻力(观)"
            color = Fore.YELLOW

        # --- 买点逻辑 (Low Suction) ---
        # 价格在均价线下方，且接近当日最低点支撑
        elif bias < -1.5:
            # 检查是否企稳 (这里简单用距离最低价的空间判断)
            dist_to_low = (current_price - low) / low * 100
            if dist_to_low < 0.5:  # 距离最低价很近
                signal = "💎深水支撑(买)"
                color = Fore.RED
            else:
                signal = "💧均线下(观)"
                color = Fore.CYAN

        # --- 均价线博弈 ---
        elif abs(bias) < 0.3:
            signal = "⚖️均价线缠绕"
            color = Fore.WHITE

        return signal, color, bias

    def fetch_minute_trend(self, ts_code):
        """
        [可选] 获取1分钟K线，判断短线趋势
        注意：这会消耗较多请求，仅对持仓股开启
        """
        try:
            # 获取最近 10 根 1分钟 K线
            df_min = self.ts_manager.pro.rt_min(ts_code=ts_code, freq='1MIN')
            if df_min.empty: return "无数据"

            # 简单的趋势判断：看最后两根K线的收盘价
            closes = df_min['close'].tolist()
            if len(closes) >= 2:
                delta = closes[-1] - closes[-2]
                if delta > 0: return f"{Fore.RED}↑微升{Style.RESET_ALL}"
                if delta < 0: return f"{Fore.GREEN}↓微跌{Style.RESET_ALL}"
            return "走平"
        except:
            return ""

    def refresh(self):
        if not self.target_codes: return

        # 1. 获取 rt_k 数据 (基础行情)
        # rt_k 支持批量，用逗号分隔
        code_list = list(self.target_codes)[:100]  # 限制一次100个防止URL过长
        codes_str = ",".join(code_list)

        try:
            df = self.ts_manager.pro.rt_k(ts_code=codes_str)
        except Exception as e:
            print(f"{Fore.RED}数据拉取失败: {e}")
            return

        if df.empty: return

        # 2. 处理数据
        results = []
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            pure_code = ts_code.split('.')[0]

            # 计算 PCT (rt_k 可能需要手动算)
            # 注意：rt_k 返回的 open/high/low/close 是当日实时数据
            pct_chg = (row['close'] - row['pre_close']) / row['pre_close'] * 100
            row['pct_chg'] = pct_chg  # 存回去方便后面用

            # --- 核心：计算 VWAP (分时均价) ---
            # amount 是元，vol 是股
            vwap = 0
            if row['vol'] > 0:
                vwap = row['amount'] / row['vol']

            # 如果没成交量(比如停牌或集合竞价刚开始)，用开盘价代替
            if vwap == 0: vwap = row['open']

            # --- 获取做T信号 ---
            t_signal, t_color, bias = self.calculate_t_signal(row, vwap)

            # --- 持仓股额外获取分钟趋势 ---
            min_trend = ""
            is_holding = pure_code in self.holdings
            if is_holding:
                # 稍微延迟一下防止QPS过高
                # min_trend = self.fetch_minute_trend(ts_code)
                pass  # 暂不开启rt_min循环，保证刷新速度，需要的放开注释

            # --- 格式化显示 ---
            name = self.strategy_map.get(pure_code, {}).get('name', row['name'])
            tag = self.strategy_map.get(pure_code, {}).get('tag', '')

            if is_holding:
                name = f"{Fore.MAGENTA}{name}{Style.RESET_ALL}"
                tag = f"{Fore.MAGENTA}[持仓]{Style.RESET_ALL} {tag}"

            # 涨幅颜色
            pct_color = Fore.RED if pct_chg > 0 else (Fore.GREEN if pct_chg < 0 else Fore.WHITE)

            # 现价相对于均价的状态
            price_str = f"{row['close']:.2f}"
            if row['close'] > vwap:  # 均价线上方
                price_str = f"{Fore.RED}{price_str}↑{Style.RESET_ALL}"
            else:  # 均价线下方
                price_str = f"{Fore.GREEN}{price_str}↓{Style.RESET_ALL}"

            results.append({
                'code': pure_code,
                'name': name,
                'pct': pct_chg,
                'pct_str': f"{pct_color}{pct_chg:>6.2f}%{Style.RESET_ALL}",
                'price_show': price_str,
                'vwap': vwap,
                'bias': bias,  # 乖离率
                'signal': f"{t_color}{t_signal}{Style.RESET_ALL}",
                'high': row['high'],
                'low': row['low'],
                'tag': tag,
                'is_holding': is_holding
            })

        # 3. 排序：持仓优先 -> 信号强度(乖离率绝对值大) -> 涨幅
        results.sort(key=lambda x: (x['is_holding'], abs(x['bias'])), reverse=True)

        # 4. 打印界面
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{Back.BLUE}{Fore.WHITE} 🔭 做T辅助雷达 (Intraday T+) {Style.RESET_ALL} | 均价线战法")
        print("-" * 125)
        print(
            f"{'代码':<8}{'名称':<14}{'涨幅':<10}{'现价/趋势':<12}{'均价线':<10}{'乖离率%':<10}{'今日区间(低-高)':<18}{'AI做T信号':<16}{'标签'}")
        print("-" * 125)

        for r in results[:40]:  # 只看前40个
            # 格式化乖离率
            bias_str = f"{r['bias']:.2f}%"
            if r['bias'] > 0: bias_str = f"+{bias_str}"

            # 格式化区间
            range_str = f"{r['low']:.2f} - {r['high']:.2f}"

            print(
                f"{r['code']:<8}"
                f"{r['name']:<24}"
                f"{r['pct_str']:<20}"
                f"{r['price_show']:<21}"
                f"{r['vwap']:<10.2f}"
                f"{bias_str:<10}"
                f"{range_str:<22}"
                f"{r['signal']:<24}"
                f"{Fore.CYAN}{r['tag']}{Style.RESET_ALL}"
            )
        print("-" * 125)
        print(
            "💡 说明: 现价红箭头↑表示在均价线上方(强势/抛压区)，绿箭头↓表示在均价线下方(弱势/吸筹区)。乖离率过大(>2.5%)宜抛，过小(<-1.5%)宜吸。")

    def run_loop(self):
        self.load_resources()
        print("\n🚀 启动做T监控，数据源: Tushare V3 rt_k ...")
        try:
            while True:
                self.refresh()
                # 刷新频率控制：3秒一次，rt_k 接口通常能够承受
                time.sleep(3)
        except KeyboardInterrupt:
            print("\n👋 停止监控")


if __name__ == "__main__":
    IntradayMonitorV2().run_loop()