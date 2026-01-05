# ==============================================================================
# 🔫 F佬/Bo佬 竞价狙击手 (src/monitors/auction_sniper.py) - v1.0
# ==============================================================================
# 功能：专门用于 9:15 - 9:30 监控竞价质量，识别“诱多核按钮”与“弱转强承接”
# 核心逻辑：记录竞价全过程，计算回撤率与承接力度
# 使用时间：每天 09:15 准时启动
# ==============================================================================

import requests
import pandas as pd
import time
import os
import re
import sys
import numpy as np
from colorama import init, Fore, Style, Back

# 适配 Windows
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
CSV_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')

# ================= 💾 内存记录仪 =================
# 格式: { 'code': {'history': [], 'max_pct': -20, 'min_pct': 20, 'start_vol': 0} }
AUCTION_RECORDER = {}


# ================= 🛠️ 数据加载 (复用逻辑) =================
def load_all_pools():
    """加载策略池+持仓+剪贴板"""
    pool = []
    seen = set()

    # 1. 辅助函数
    def load_from_file(path, source_tag, is_holdings=False):
        if not os.path.exists(path): return
        try:
            enc = 'utf-8'
            try:
                pd.read_csv(path, encoding='utf-8')
            except:
                enc = 'gbk'

            if path.endswith('.csv'):
                df = pd.read_csv(path, encoding=enc, dtype=str)
            else:
                # 简单处理txt
                with open(path, 'r', encoding=enc) as f:
                    lines = f.readlines()
                rows = []
                for line in lines:
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) >= 2 and parts[0].isdigit():
                        rows.append({'code': parts[0], 'name': parts[1]})
                df = pd.DataFrame(rows)

            for _, row in df.iterrows():
                code = str(row.get('code', ''))
                if len(code) != 6: continue
                if code in seen: continue

                sina_code = f"sz{code}" if code.startswith(('0', '3')) else f"sh{code}"
                name = row.get('name', '-')
                tag = row.get('tag', source_tag)
                if is_holdings: tag = f"持仓/{name}"

                pool.append({
                    'sina_code': sina_code, 'name': name, 'code': code, 'tag': tag
                })
                seen.add(code)
        except Exception as e:
            pass

    load_from_file(HOLDINGS_PATH, "持仓", True)
    load_from_file(CSV_PATH, "策略池")
    load_from_file(THS_PATH, "剪贴板")

    return pool


# ================= 📊 竞价数据获取 =================
def fetch_auction_data(codes):
    if not codes: return {}
    url = f"http://hq.sinajs.cn/list={','.join(codes)}"
    headers = {'Referer': 'https://finance.sina.com.cn'}

    data_map = {}
    try:
        resp = requests.get(url, headers=headers, timeout=2)
        resp.encoding = 'gbk'
        for line in resp.text.strip().split('\n'):
            if not line: continue
            parts = line.split('=')
            code = parts[0].split('_')[-1]
            val = parts[1].strip('"')
            d = val.split(',')
            if len(d) < 30: continue  # 竞价期间数据可能不全，但通常要有买一买五

            # 解析关键数据
            open_p = float(d[1])  # 开盘价 (9:25前是试盘价)
            pre_c = float(d[2])
            curr_p = float(d[3])  # 当前价

            # 竞价期间 curr_p 经常是 0，用 bid1_price 代替或者 open_p
            price = curr_p if curr_p > 0 else open_p
            if price == 0: price = pre_c  # 还没开出来

            pct = (price - pre_c) / pre_c * 100

            # 计算承接力：买1-买5的总挂单量 (手)
            # d[10] 是买1量, d[12] 是买2量...
            bid_vol_sum = (int(d[10]) + int(d[12]) + int(d[14]) + int(d[16]) + int(d[18])) // 100

            # 总成交量
            total_vol = int(d[8]) // 100

            data_map[code] = {
                'pct': pct,
                'price': price,
                'bid_vol': bid_vol_sum,
                'total_vol': total_vol,
                'time': time.strftime("%H:%M:%S")
            }
    except:
        pass
    return data_map


# ================= 🧠 质量分析算法 =================
def analyze_quality(code, current_data):
    # 初始化记录
    if code not in AUCTION_RECORDER:
        AUCTION_RECORDER[code] = {
            'history': [],
            'max_pct': -20,
            'start_bid': current_data['bid_vol']
        }

    rec = AUCTION_RECORDER[code]
    rec['history'].append(current_data)

    # 更新最高涨幅 (用于计算回撤)
    if current_data['pct'] > rec['max_pct']:
        rec['max_pct'] = current_data['pct']

    # 计算核心指标
    max_p = rec['max_pct']
    curr_p = current_data['pct']

    # 1. 回撤幅度 (Retracement)
    # 如果最高是 10%，现在是 5%，差值是 5
    retracement = max_p - curr_p

    # 2. 承接增量 (Support Growth)
    # 现在的买单量 vs 最开始记录时的买单量
    # 如果是负数，说明撤单严重
    support_growth = current_data['bid_vol'] - rec['start_bid']

    # 3. 判定逻辑
    decision = ""
    score = 0

    # A. 诱多核按钮判定 (鲁信模式)
    # 曾摸涨停(>9.5)，回撤巨大(>3)，且承接一般
    if max_p > 9.5 and retracement > 4.0:
        decision = f"{Back.GREEN}{Fore.WHITE}🤮诱多核按钮{Style.RESET_ALL}"
        score = -10

    # B. 弱转强/抢筹判定 (海格模式)
    # 曾摸高(>5)，回撤小(<2)，且承接大幅增加(>1000手)
    elif retracement < 2.0 and support_growth > 1000 and curr_p > 2.0:
        decision = f"{Back.RED}{Fore.WHITE}🔥抢筹强承接{Style.RESET_ALL}"
        score = 10

    # C. 尴尬区判定
    elif 3.0 < curr_p < 7.0:
        if retracement > 3.0:
            decision = f"{Fore.GREEN}📉大幅回落{Style.RESET_ALL}"
        elif support_growth < 0:
            decision = f"{Fore.YELLOW}⚠️撤单严重{Style.RESET_ALL}"
        else:
            decision = f"{Fore.CYAN}观察承接{Style.RESET_ALL}"

    # D. 一字板
    elif curr_p > 9.8 and retracement < 0.1:
        decision = f"{Fore.RED}🔒一字封死{Style.RESET_ALL}"

    else:
        decision = "观察"

    return {
        'max_pct': max_p,
        'retracement': retracement,
        'bid_vol': current_data['bid_vol'],
        'decision': decision,
        'score': score
    }


# ================= 🔄 主循环 =================
def run_sniper():
    pool = load_all_pools()
    codes = [item['sina_code'] for item in pool]

    print(f"{Fore.CYAN}🔫 竞价狙击手已就位，监控标的: {len(codes)} 只{Style.RESET_ALL}")
    print("等待 9:15 开盘...")

    while True:
        now = time.strftime("%H:%M:%S")

        # 1. 抓取数据
        raw_data = fetch_auction_data(codes)

        # 2. 组装结果
        display_list = []
        for item in pool:
            code = item['sina_code']
            if code in raw_data:
                # 分析
                res = analyze_quality(code, raw_data[code])

                # 过滤显示：只显示有波动的，或者在策略池里的重点
                # 如果涨幅很小且没动静，就不显示了，刷屏太快
                if abs(raw_data[code]['pct']) > 1.0 or res['retracement'] > 1.0:
                    display_list.append({
                        'name': item['name'],
                        'tag': item['tag'],
                        'curr_pct': raw_data[code]['pct'],
                        'max_pct': res['max_pct'],
                        'drop': res['retracement'],
                        'bid': res['bid_vol'],
                        'decision': res['decision'],
                        'score': res['score']
                    })

        # 3. 排序：按【关注度/分数】排序
        # 负分(核按钮)排前面警示，正分(抢筹)也排前面
        display_list.sort(key=lambda x: abs(x['score']), reverse=True)

        # 4. 刷新屏幕
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 120)
        print(f"🔫 竞价狙击实时监控 | 时间: {now} | {Fore.YELLOW}9:25后定格{Style.RESET_ALL}")
        print("=" * 120)
        print(f"{'名称':<8} {'当前%':<8} {'最高%':<8} {'回撤%':<8} {'买盘承接(手)':<12} {'AI诊断结果'}")
        print("-" * 120)

        for row in display_list[:30]:  # 只看前30个活跃的
            # 颜色处理
            pct_str = f"{row['curr_pct']:.2f}%"
            if row['curr_pct'] > 0:
                pct_str = Fore.RED + pct_str + Style.RESET_ALL
            else:
                pct_str = Fore.GREEN + pct_str + Style.RESET_ALL

            drop_str = f"{row['drop']:.1f}%"
            if row['drop'] > 3.0: drop_str = Back.GREEN + Fore.WHITE + drop_str + Style.RESET_ALL

            print(
                f"{row['name']:<8} {pct_str:<18} {row['max_pct']:<8.1f} {drop_str:<18} {row['bid']:<12} {row['decision']}")

        print("=" * 120)

        # 9:25:10 自动退出，防止影响盘中脚本
        if now > "09:25:10":
            print(f"\n{Fore.RED}🛑 竞价结束，请记录数据或截图，准备切换到盘中监控脚本。{Style.RESET_ALL}")
            break

        time.sleep(3)


if __name__ == "__main__":
    run_sniper()