# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/live_watch.py)
# v6.4 决战版 (本地Table做分母 + 9:25 API做分子)
# ==============================================================================
import akshare as ak
import pandas as pd
import time
import os
import json
import re
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

# 指向你今晚导出的文件 (明天早上它就是“昨日数据”)
THS_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths', 'Table.txt')

# 缓存
AUCTION_CACHE = {}
LOCAL_HISTORY_MAP = {}  # 改名：明确这是历史/背景板数据


# ================= 🛠️ 1. 读取本地作为“昨日基准” =================

def clean_unit(val):
    """清洗单位"""
    if pd.isna(val) or str(val).strip() == '--': return 0.0
    s = str(val).replace(',', '').replace(' ', '')
    try:
        if '亿' in s: return float(s.replace('亿', '')) * 100000000
        if '万' in s: return float(s.replace('万', '')) * 10000
        if '%' in s: return float(s.replace('%', ''))
        return float(s)
    except:
        return 0.0


def load_yesterday_baseline():
    """
    🔥 核心逻辑：读取 Table.txt，将其视为【昨日数据】
    这里的 '成交额' = 昨日成交额 (yest_amt)
    这里的 '流通市值' = 流通市值 (circ_mv)
    """
    global LOCAL_HISTORY_MAP
    if not os.path.exists(THS_DATA_PATH):
        print(f"{Fore.RED}❌ 警告：未找到昨日数据文件 {THS_DATA_PATH}！无法计算竞价爆量比！{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}正在加载昨日基准数据 (作为分母)...{Style.RESET_ALL}")
    df = pd.DataFrame()
    try:
        # 尝试多种编码读取
        try:
            df = pd.read_csv(THS_DATA_PATH, sep=r'\t+', engine='python', encoding='gbk', dtype=str)
        except:
            df = pd.read_csv(THS_DATA_PATH, sep=r'\t+', engine='python', encoding='utf-8', dtype=str)
    except:
        pass

    if df.empty: return

    # 清洗列名
    df.columns = [str(c).strip() for c in df.columns]

    col_code = next((c for c in df.columns if '代码' in c), None)
    col_name = next((c for c in df.columns if '名称' in c), None)
    col_circ_mv = next((c for c in df.columns if '流通市值' in c), None)
    # 关键：这个文件里的“成交额”就是昨天的量！
    col_amt = next((c for c in df.columns if '金额' in c or '成交额' in c), None)

    count = 0
    for _, row in df.iterrows():
        try:
            raw_code = str(row[col_code])
            code = re.sub(r'\D', '', raw_code)
            if len(code) != 6: continue

            item = {
                'name': str(row[col_name]),
                'circ_mv': clean_unit(row.get(col_circ_mv, 0)),
                'yest_amt': clean_unit(row.get(col_amt, 0))  # 🔥 存为昨日成交
            }
            LOCAL_HISTORY_MAP[code] = item
            count += 1
        except:
            continue
    print(f"{Fore.GREEN}✅ 已加载 {count} 条基准数据。准备迎接 9:25 实战！{Style.RESET_ALL}")


# ================= 🛠️ 2. API 获取 9:25 实时数据 =================

def fetch_live_auction_data(pool):
    """
    强制联网获取 9:25 的数据
    """
    codes = [p['code'] for p in pool]
    # 如果池子太大，分批请求防止超时
    # 这里简单处理，一次请求所有
    try:
        # akshare 的 spot 接口在 9:25 返回的就是竞价结果
        df = ak.stock_zh_a_spot_em()
        if df.empty: return {}

        # 过滤出我们的池子
        df = df[df['代码'].isin(codes)]

        res = {}
        for _, row in df.iterrows():
            code = row['代码']
            # 9:25 时：
            # 最新价 = 开盘价
            # 成交额 = 竞价成交额
            # 涨跌幅 = 竞价涨幅
            res[code] = {
                'open_pct': float(row['涨跌幅']),
                'curr_p': float(row['最新价']),
                'auction_amt': float(row['成交额'])  # 🔥 此时此刻的成交额 = 竞价金额
            }
        return res
    except Exception as e:
        print(f"API Error: {e}")
        return {}


# ================= 🧠 3. 核心决策 (计算爆量) =================

def get_decision(item):
    # 分子：今日9:25竞价金额 (来自 API)
    auc_amt = item.get('auction_amt', 0)

    # 分母：昨日全天成交额 & 流通市值 (来自 本地文件)
    yest_amt = item.get('yest_amt', 0)
    circ_mv = item.get('circ_mv', 0)

    # 竞价涨幅 (来自 API)
    open_pct = item.get('open_pct', 0)

    # 指标计算
    ratio_total = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0
    ratio_circ = (auc_amt / circ_mv * 100) if circ_mv > 0 else 0

    item['r_total'] = ratio_total
    item['r_circ'] = ratio_circ

    # --- 判定逻辑 ---

    # 1. 过滤垃圾
    if open_pct < -2.0: return f"低开({open_pct}%)", 0
    if open_pct < 2.0: return f"弱竞价({open_pct}%)", 0

    # 2. 1进2 核心公式
    # 完美标准：竞价/昨日 > 5% 且 竞价/市值 > 1.5% (根据你的经验调整)
    is_perfect = False

    # 爆量检测
    if 5.0 <= ratio_total <= 20.0:  # 竞价占昨日 5%~20% (过低没量，过高是加速/一字)
        if ratio_circ >= 1.5:  # 换手够了
            is_perfect = True

    # 一字板特判
    if open_pct > 9.8:
        if ratio_total > 5.0:
            return f"{Fore.MAGENTA}一字爆量{Style.RESET_ALL}", 80
        return f"{Fore.CYAN}一字板{Style.RESET_ALL}", 0

    if is_perfect:
        return f"{Back.RED}{Fore.WHITE} 🔥 完美1进2 {Style.RESET_ALL}", 95

    # 达标但不够完美
    if ratio_total > 3.0 and open_pct > 3.0:
        return f"{Fore.RED}★ 达标关注{Style.RESET_ALL}", 70

    return f"观察(量{ratio_total:.1f}%)", 40


# ================= 🔄 主循环 =================

def load_strategy_pool():
    # 读取 strategy_pool.csv
    df = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, dtype={'code': str})
        except:
            pass
    if df.empty: return []
    return df.to_dict('records')


def monitor_loop(pool):
    # 1. 获取实时数据 (API)
    live_data = fetch_live_auction_data(pool)
    if not live_data:
        print("\r等待 9:15 开盘数据...", end="")
        return

    display_list = []

    for item in pool:
        code = item['code']

        # 基础信息
        name = item.get('name', '-')

        # 1. 融合昨日数据 (分母)
        if code in LOCAL_HISTORY_MAP:
            item['yest_amt'] = LOCAL_HISTORY_MAP[code]['yest_amt']
            item['circ_mv'] = LOCAL_HISTORY_MAP[code]['circ_mv']
        else:
            # 如果本地没匹配到，就没法算指标，跳过或给默认
            item['yest_amt'] = 0
            item['circ_mv'] = 0

        # 2. 融合今日数据 (分子)
        if code in live_data:
            item['auction_amt'] = live_data[code]['auction_amt']
            item['open_pct'] = live_data[code]['open_pct']
            item['curr_p'] = live_data[code]['curr_p']
        else:
            item['auction_amt'] = 0
            item['open_pct'] = 0
            item['curr_p'] = 0

        # 3. 决策
        decision, score = get_decision(item)
        item['decision'] = decision
        item['score'] = score

        display_list.append(item)

    # 排序：按分数降序
    display_list.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    # 刷新显示
    os.system('cls' if os.name == 'nt' else 'clear')
    print(
        f"{Back.RED}{Fore.WHITE} ⚔️ 明日决战 9:25 竞价监控 ⚔️ {Style.RESET_ALL} | {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 130)
    print(f"{'代码':<7} {'名称':<8} {'竞价%':<7} {'竞价额(亿)':<11} {'竞/昨%':<8} {'竞/流%':<8} {'AI决策'}")
    print("-" * 130)

    for p in display_list:
        if p['score'] < 40: continue  # 过滤杂鱼

        auc_yi = p['auction_amt'] / 100000000

        # 高亮数据
        r_total_str = f"{p['r_total']:.1f}"
        if 5 <= p['r_total'] <= 15: r_total_str = f"{Fore.RED}{r_total_str}{Style.RESET_ALL}"

        r_circ_str = f"{p['r_circ']:.2f}"
        if p['r_circ'] >= 1.5: r_circ_str = f"{Fore.MAGENTA}{r_circ_str}{Style.RESET_ALL}"

        pct_color = Fore.RED if p['open_pct'] > 0 else Fore.GREEN

        print(
            f"{p['code']:<7} {p['name'][:4]:<8} {pct_color}{p['open_pct']:<7.2f}{Style.RESET_ALL} {auc_yi:<11.2f} {r_total_str:<8} {r_circ_str:<8} {p['decision']}")
    print("=" * 130)


if __name__ == "__main__":
    # 1. 先加载昨天的基准数据 (Table.txt)
    load_yesterday_baseline()

    # 2. 加载监控池
    pool = load_strategy_pool()
    print(f"监控池大小: {len(pool)} 只")

    print("\n等待 9:25 数据更新...")
    try:
        while True:
            # 只有在 9:15 之后才开始疯狂请求，避免被封
            now = datetime.datetime.now().strftime("%H:%M")
            if now >= "09:15":
                monitor_loop(pool)
            else:
                print(f"\r当前时间 {now}，脚本待机中...", end="")

            time.sleep(3)  # 3秒刷一次
    except KeyboardInterrupt:
        pass