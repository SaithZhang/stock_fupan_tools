# src/strategies/order_flow.py
# ==============================================================================
# 🌊 资金流雷达 (Order Flow Monitor - V2.1 防封调试版)
# 修复：增加请求头伪装，增加原始数据调试打印
# ==============================================================================

import time
import requests
import os
import random
from colorama import init, Fore, Style

init(autoreset=True)


class OrderFlowMonitor:
    def __init__(self, code, threshold_vol=100):
        """
        :param code: 股票代码 (如 000815)
        :param threshold_vol: 大单阈值 (手)
        """
        self.code = code
        self.threshold = threshold_vol
        # 腾讯前缀适配
        if code.startswith('6'):
            self.symbol = f"sh{code}"
        elif code.startswith('4') or code.startswith('8'):
            self.symbol = f"bj{code}"
        else:
            self.symbol = f"sz{code}"

    def get_headers(self):
        """随机User-Agent防封"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        return {"User-Agent": random.choice(user_agents)}

    def get_ticks(self):
        """获取最近的逐笔成交"""
        try:
            # 腾讯逐笔接口 (p=0 获取最新一页)
            url = f"http://stock.gtimg.cn/data/index.php?appn=detail&action=data&c={self.symbol}&p=0"

            # 增加 timeout 和 headers
            r = requests.get(url, timeout=5, headers=self.get_headers())

            if r.status_code != 200:
                print(f"{Fore.RED}❌ HTTP错误: {r.status_code}{Style.RESET_ALL}")
                return None

            if not r.text:
                print(f"{Fore.RED}❌ 返回内容为空{Style.RESET_ALL}")
                return None

            # 调试：打印一下原始返回的前50个字符，看看是不是被封了
            # 正常格式应为: v_detail_data_sz000815="0|..."
            if "v_detail_data" not in r.text:
                print(f"{Fore.YELLOW}⚠️ 原始响应异常: {r.text[:50]}...{Style.RESET_ALL}")
                return None

            # 数据清洗
            content = r.text.split('"')[1]
            raw_ticks = content.split('|')

            ticks = []
            for t in raw_ticks:
                if not t: continue
                parts = t.split('/')

                # --- 智能格式识别 ---
                try:
                    # 寻找包含时间 ':' 的列索引
                    time_idx = -1
                    if len(parts) > 0 and ':' in parts[0]:
                        time_idx = 0
                    elif len(parts) > 1 and ':' in parts[1]:
                        time_idx = 1

                    if time_idx == -1 or len(parts) < time_idx + 4:
                        continue

                    # [Time, Price, Vol, Type]
                    _time = parts[time_idx]
                    _price = float(parts[time_idx + 1])
                    _vol = int(parts[time_idx + 2])
                    _type = parts[time_idx + 3]  # B/S/M

                    ticks.append({
                        'time': _time,
                        'price': _price,
                        'vol': _vol,
                        'type': _type
                    })
                except ValueError:
                    continue

            return ticks
        except Exception as e:
            print(f"{Fore.RED}❌ 请求异常: {e}{Style.RESET_ALL}")
            return None

    def analyze(self):
        ticks = self.get_ticks()
        if not ticks:
            # 只有在真的获取不到数据时才打印这个，避免刷屏
            print(f"⚠️ {self.code} 暂无数据 (可能是午休或接口限制)...")
            return

        # 只看最近 30 笔交易
        recent_ticks = ticks[-30:]

        buy_vol = 0
        sell_vol = 0
        big_buy_count = 0
        big_sell_count = 0

        last_price = recent_ticks[-1]['price']
        last_time = recent_ticks[-1]['time']

        print("-" * 60)
        print(f"🌊 资金流速报 [{self.code}] @ {last_time} (现价: {last_price})")
        print("-" * 60)

        for t in recent_ticks:
            is_big = t['vol'] >= self.threshold
            vol_str = str(t['vol'])

            if is_big:
                vol_str = f"{Fore.YELLOW}{t['vol']}{Style.RESET_ALL}"

            type_str = t['type']
            type_show = "中性"
            if type_str == 'B':
                buy_vol += t['vol']
                type_show = f"{Fore.RED}主买{Style.RESET_ALL}"
                if is_big: big_buy_count += 1
            elif type_str == 'S':
                sell_vol += t['vol']
                type_show = f"{Fore.GREEN}主卖{Style.RESET_ALL}"
                if is_big: big_sell_count += 1

            if is_big:  # 只打印大单
                print(f"   > {t['time']}  {t['price']:<6}  {type_show}  {vol_str} 手")

        net_vol = buy_vol - sell_vol

        print("-" * 60)
        print(f"📊 最近30笔力度 (阈值:{self.threshold}手):")
        print(f"   🔴 主买: {buy_vol:<6} 🟢 主卖: {sell_vol}")

        if net_vol > 0:
            print(f"   🔥 净流入: {Fore.RED}+{net_vol} 手{Style.RESET_ALL}")
        else:
            print(f"   ❄️ 净流出: {Fore.GREEN}{net_vol} 手{Style.RESET_ALL}")
        print("-" * 60)


if __name__ == "__main__":
    target_code = "000815"  # 可以在这里改代码
    monitor = OrderFlowMonitor(target_code)

    print(f"🚀 启动资金流监控: {target_code} (按 Ctrl+C 退出)")
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            monitor.analyze()
            print(f"刷新中... (3s) {time.strftime('%H:%M:%S')}")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n👋 停止监控")