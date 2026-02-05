# src/strategies/t_assistant.py
# ==============================================================================
# 🕵️‍♂️ 做T 辅助雷达 (V3.1 智能修正版)
# 修复：腾讯接口返回“累计成交额”导致均价计算错误的问题
# 新增：自动识别数据列含义，智能计算 VWAP
# ==============================================================================

import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from colorama import init, Fore, Style
import warnings
import re

# 忽略 pandas 的计算警告
warnings.filterwarnings('ignore')
init(autoreset=True)

# --- 配置路径 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')


class T_Trade_Assistant:
    def __init__(self):
        self.holdings = {}
        self.BIAS_THRESHOLD_HIGH = 1.5
        self.BIAS_THRESHOLD_LOW = -1.5

    def load_holdings(self):
        """从文件读取持仓代码"""
        if not os.path.exists(HOLDINGS_PATH):
            return {'000815': '美利云(测试)'}

        holdings = {}
        try:
            with open(HOLDINGS_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split()
                match = re.search(r'\d{6}', parts[0])
                if not match: continue
                code = match.group(0)
                name = parts[1] if len(parts) > 1 else code
                holdings[code] = name
            return holdings
        except Exception as e:
            print(f"{Fore.RED}❌ 读取持仓失败: {e}")
            return {}

    def get_market_volume(self):
        """获取上证指数成交额"""
        try:
            url = "http://qt.gtimg.cn/q=sh000001"
            r = requests.get(url, timeout=1)
            data = r.text.split('~')
            if len(data) > 37:
                amount_wan = float(data[37])
                return amount_wan * 10000
            return 0
        except:
            return 0

    def get_tencent_minute_data(self, code):
        """获取腾讯分时数据 (含智能清洗)"""
        if code.startswith('6'):
            prefix = 'sh'
        elif code.startswith('4') or code.startswith('8'):
            prefix = 'bj'
        else:
            prefix = 'sz'

        symbol = f"{prefix}{code}"
        url = f"http://web.ifzq.gtimg.cn/appstock/app/minute/query?code={symbol}"

        try:
            r = requests.get(url, timeout=3)
            data = r.json()
            min_data = data['data'][symbol]['data']['data']

            # 1. 清洗字符串数据 ["0930 10.5 100 200", ...] -> DataFrame
            cleaned_data = []
            for item in min_data:
                if isinstance(item, str):
                    cleaned_data.append(item.split())
                else:
                    cleaned_data.append(item)

            # 2. 转换为 DataFrame
            # 腾讯标准格式: [time, close, cum_volume, cum_amount(可能)]
            df = pd.DataFrame(cleaned_data)
            df = df.iloc[:, :4]
            df.columns = ['time', 'close', 'col3', 'col4']

            df['close'] = df['close'].astype(float)
            df['col3'] = df['col3'].astype(float)  # 通常是累计成交量
            df['col4'] = df['col4'].astype(float)  # 通常是累计成交额

            # --- 🛠️ 智能计算 VWAP (均价) ---
            # 逻辑：如果 col4 数值巨大（远超股价），说明它是成交额，需要除以成交量
            # 如果 col4 和股价接近，说明它已经是均价了

            last_price = df['close'].iloc[-1]
            check_val = df['col4'].iloc[-1]

            if check_val > last_price * 100:
                # 判定为成交额，需要计算: 均价 = 成交额 / (成交量 * 100)
                # 注意：腾讯的成交量单位通常是“手”
                # 避免除以0
                df['avg_price'] = np.where(
                    df['col3'] > 0,
                    df['col4'] / (df['col3'] * 100),
                    df['close']
                )
            else:
                # 判定已经是均价
                df['avg_price'] = df['col4']

            return df

        except Exception as e:
            # print(f"数据解析错误: {e}")
            return None

    def calculate_indicators(self, df):
        """计算指标"""
        if df is None or len(df) < 5: return None

        # MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2
        df['macd'] = macd

        # 涨速
        df['pct_change'] = df['close'].pct_change() * 100
        return df

    def analyze_stock(self, code, name):
        df = self.get_tencent_minute_data(code)
        if df is None: return None

        df = self.calculate_indicators(df)
        if df is None: return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. 乖离率
        vwap = curr['avg_price']
        price = curr['close']

        # 防错：如果计算出的 VWAP 极度离谱（比如还是0），强制等于现价
        if vwap <= 0 or vwap > price * 2 or vwap < price * 0.5:
            bias = 0
            bias_display = "计算异常"
        else:
            bias = (price - vwap) / vwap * 100
            bias_display = f"{bias:.2f}%"

        # 2. MACD 趋势
        macd_val = curr['macd']
        macd_prev = prev['macd']

        macd_trend = "走平"
        if macd_val > 0:
            if macd_val < macd_prev:
                macd_trend = f"{Fore.GREEN}红柱缩短(转弱){Style.RESET_ALL}"
            else:
                macd_trend = f"{Fore.RED}红柱变长(冲高){Style.RESET_ALL}"
        else:
            if macd_val > macd_prev:
                macd_trend = f"{Fore.RED}绿柱缩短(企稳){Style.RESET_ALL}"
            else:
                macd_trend = f"{Fore.GREEN}绿柱变长(杀跌){Style.RESET_ALL}"

        # 3. 建议
        advice = "观望"
        advice_color = Fore.WHITE

        if curr['pct_change'] > 0.5:
            advice = "🚀 急拉关注";
            advice_color = Fore.MAGENTA
        elif curr['pct_change'] < -0.5:
            advice = "📉 急跌小心";
            advice_color = Fore.GREEN
        elif bias > self.BIAS_THRESHOLD_HIGH:
            advice = "⚠️ 准备高抛";
            advice_color = Fore.YELLOW
            if macd_val < macd_prev: advice = "⚡️ 立刻卖出(背离)"; advice_color = Fore.RED
        elif bias < self.BIAS_THRESHOLD_LOW:
            advice = "👀 准备低吸";
            advice_color = Fore.CYAN
            if macd_val > macd_prev: advice = "💰 立刻买入(企稳)"; advice_color = Fore.MAGENTA

        return {
            'code': code, 'name': name, 'price': price, 'vwap': vwap,
            'bias': bias, 'bias_str': bias_display,
            'macd_trend': macd_trend, 'advice': advice,
            'color': advice_color, 'time': curr['time']
        }

    def run(self):
        self.holdings = self.load_holdings()
        print(f"\n🚀 做T 助手启动... 监控 {len(self.holdings)} 只标的")

        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n🚀 做T 助手运行中... [Ctrl+C 退出] {time.strftime('%H:%M:%S')}")
            print(
                f"{'时间':<6} {'代码':<8} {'名称':<10} {'现价':<8} {'均价(黄线)':<10} {'乖离率':<12} {'MACD状态':<18} {'操作建议'}")
            print("-" * 95)

            for code, name in self.holdings.items():
                try:
                    res = self.analyze_stock(code, name)
                    if res:
                        # 乖离率颜色
                        bias_raw = res['bias']
                        if bias_raw > 0:
                            bias_show = f"{Fore.RED}+{res['bias_str']}{Style.RESET_ALL}"
                        elif bias_raw < 0:
                            bias_show = f"{Fore.GREEN}{res['bias_str']}{Style.RESET_ALL}"
                        else:
                            bias_show = res['bias_str']

                        print(
                            f"{res['time']:<6} "
                            f"{res['code']:<8} "
                            f"{res['name']:<10} "
                            f"{res['price']:<8.2f} "
                            f"{res['vwap']:<10.2f} "
                            f"{bias_show:<21} "
                            f"{res['macd_trend']:<27} "
                            f"{res['color']}{res['advice']}{Style.RESET_ALL}"
                        )
                    else:
                        print(f"xx:xx  {code:<8} {name:<10} 数据获取中...")
                except Exception as e:
                    print(f"xx:xx  {code:<8} {name:<10} {e}")

            m_vol = self.get_market_volume()
            vol_str = f"{int(m_vol / 100000000)}亿"
            print("-" * 95)
            print(f"📊 上证成交额: {Fore.YELLOW}{vol_str}{Style.RESET_ALL}")

            time.sleep(10)


if __name__ == "__main__":
    try:
        T_Trade_Assistant().run()
    except KeyboardInterrupt:
        print("\n👋 程序已停止")