# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py)
# v4.3 修复版 (修复历史数据为0的问题)
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

# 适配 Windows 控制台
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径与配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
CSV_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'db', 'stock_concepts.json')
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

HOT_TOPICS = ["机器人", "航天", "AI", "消费电子", "算力", "低空", "固态", "军工", "卫星", "脑机", "信创", "华为", "蛇"]

# 全局内存变量
AUCTION_CACHE = {}  # 今日竞价金额 {code: amount}
HISTORY_CACHE = {}  # 历史数据缓存


# ================= 🛠️ 历史数据预加载 (核心修复) =================

def fetch_single_stock_history(code):
    """抓取单只股票的历史资金数据"""
    res = {'yest_amt': 0, 'prev_amt': 0, 'yest_auc_amt': 0, 'prev_auc_amt': 0}
    try:
        # 1. 获取日线 (最近20个交易日)
        # 注意：start_date/end_date 需要是 YYYYMMDD
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=40)).strftime("%Y%m%d")

        # 尝试抓取
        df_daily = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="")

        if not df_daily.empty:
            # 确保日期列是字符串格式，方便比较
            df_daily['日期'] = df_daily['日期'].astype(str)
            df_daily = df_daily.sort_values(by='日期', ascending=False)

            # 排除今天的日期 (YYYY-MM-DD)
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')

            # 如果最新的日期是今天，就剔除掉
            if df_daily.iloc[0]['日期'] == today_str:
                df_daily = df_daily.iloc[1:]

            # 拿最近的两天数据
            if len(df_daily) >= 1:
                res['yest_amt'] = float(df_daily.iloc[0]['成交额'])
            if len(df_daily) >= 2:
                res['prev_amt'] = float(df_daily.iloc[1]['成交额'])

        # 2. 获取分钟线 (取昨日09:30成交额)
        # 这个接口比较慢，且容易失败，做个简单保护
        # 如果获取失败，yest_auc_amt 保持为0，仅影响纵向对比，不影响横向占比(ratio)
        df_min = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
        if not df_min.empty:
            df_min['time_only'] = df_min['时间'].apply(lambda x: str(x).split(' ')[1])
            # 筛选所有 09:30:00 的K线
            df_open_bars = df_min[df_min['time_only'] == '09:30:00'].sort_values(by='时间', ascending=False)

            # 同样排除今天
            df_open_bars = df_open_bars[~df_open_bars['时间'].str.contains(today_str)]

            if len(df_open_bars) >= 1:
                res['yest_auc_amt'] = float(df_open_bars.iloc[0]['成交额'])
            if len(df_open_bars) >= 2:
                res['prev_auc_amt'] = float(df_open_bars.iloc[1]['成交额'])

    except Exception as e:
        # 出错时保持默认值0
        pass

    return code, res


def preload_history_data(pool):
    print(f"{Fore.CYAN}正在预加载历史资金数据 (修复版: 确保获取昨日数据)...{Style.RESET_ALL}")
    codes = [p['code'] for p in pool]
    # 减少并发数，防止被AkShare封IP导致获取失败
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single_stock_history, code): code for code in codes}
        c = 0
        for future in as_completed(futures):
            c += 1
            code, data = future.result()
            HISTORY_CACHE[code] = data
            print(f"\r进度: {c}/{len(codes)} | {code} 加载完毕", end="")
    print(f"\n{Fore.GREEN}✅ 历史数据加载完毕{Style.RESET_ALL}")


# ================= 🛠️ 竞价数据录制 =================

def get_today_cache_path():
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    return os.path.join(CACHE_DIR, f"auction_amount_{today_str}.json")


def save_auction_to_disk(data_dict):
    try:
        path = get_today_cache_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: old = json.load(f)
            old.update(data_dict)
            data_dict = old
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f)
    except:
        pass


def load_auction_from_disk():
    try:
        path = get_today_cache_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except:
        pass
    return {}


def mode_auction_capture(pool):
    print(f"{Back.MAGENTA}{Fore.WHITE} 🎥 进入竞价金额录制模式 (09:15-09:30) {Style.RESET_ALL}")
    while True:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if now_str > "09:30:05":
            print("\n⏰ 竞价结束，切换监控...")
            break

        codes = [p['code'] for p in pool]
        data = fetch_akshare_realtime(codes)
        if data:
            auc = {k: v['amount'] for k, v in data.items() if v['amount'] > 0}
            save_auction_to_disk(auc)
            print(f"\r[{now_str}] 录入 {len(auc)} 只标的金额...", end="")
        time.sleep(3)


def backfill_missing_today_auction(pool):
    global AUCTION_CACHE
    AUCTION_CACHE.update(load_auction_from_disk())


# ================= 🧠 核心决策逻辑 =================

def get_stock_limit(code):
    if code.startswith(('8', '4')): return 29.8
    if code.startswith(('3', '68')): return 19.8
    return 9.8


def get_smart_decision(item):
    pct = item['pct']
    open_pct = item['open_pct']
    max_pct = item['max_pct']

    # 获取最核心的两个资金数据
    # 优先取录制的竞价金额，如果没有录制到，暂用实时金额(若是盘中，这会有误差，若是竞价时段则准确)
    today_auc_amt = item.get('today_auction_amt', 0)
    yest_total_amt = item.get('history', {}).get('yest_amt', 0)

    # 计算金额占比 (Money Ratio)
    # 修复除以0的Bug
    if yest_total_amt > 0:
        ratio = (today_auc_amt / yest_total_amt) * 100
    else:
        ratio = 0.0

    item['amt_ratio'] = ratio

    limit = get_stock_limit(item['code'])
    is_limit_up = (pct >= limit)

    # 1. 熔断安全锁 (Safety Lock)
    if open_pct > 7.0:
        if ratio < 12.0: return f"{Back.GREEN}{Fore.WHITE}❌大高开量太少({ratio:.1f}%){Style.RESET_ALL}"
    elif open_pct > 4.0:
        if ratio < 8.0: return f"{Back.GREEN}{Fore.WHITE}❌高开量虚({ratio:.1f}%){Style.RESET_ALL}"
    elif open_pct > 1.0:
        if ratio < 2.5: return f"{Fore.YELLOW}量能一般{Style.RESET_ALL}"

    # 2. 状态判断
    if is_limit_up: return f"{Fore.RED}🔒涨停封板{Style.RESET_ALL}"
    if pct <= -limit: return f"{Back.GREEN}{Fore.WHITE}🤢跌停死锁{Style.RESET_ALL}"
    if max_pct >= limit and pct < limit - 2.0: return f"{Fore.YELLOW}💥炸板离场{Style.RESET_ALL}"

    # 3. 弱转强分级
    if 0 < open_pct < 6.0 and pct > 0:
        if ratio >= 10.0:
            return f"{Fore.MAGENTA}🔥爆量强更强{Style.RESET_ALL}"
        elif ratio >= 8.0:
            return f"{Fore.RED}🚀弱转强(真){Style.RESET_ALL}"
        elif ratio > 5.0:
            return f"量能勉强"

    return "💤观察"


# ================= 🛠️ 基础功能 =================

def load_concept_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def load_strategy_pool(concept_db):
    df = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, dtype={'code': str})
        except:
            pass

    if df.empty: return []
    pool = df.to_dict('records')
    for item in pool:
        code = str(item.get('code'))
        tag = str(item.get('tag', ''))
        if code in concept_db:
            item['tag_display'] = f"{tag} {concept_db[code].split('|')[0]}"
        else:
            item['tag_display'] = tag
    return pool


def fetch_akshare_realtime(codes):
    if not codes: return {}
    try:
        df = ak.stock_zh_a_spot_em()
        df = df[df['代码'].isin(codes)]
        res = {}
        for _, row in df.iterrows():
            code = row['代码']
            pre = float(row['昨收'])
            res[code] = {
                'curr_p': float(row['最新价']),
                'pct': float(row['涨跌幅']),
                'open_p': float(row['今开']),
                'open_pct': (float(row['今开']) - pre) / pre * 100 if pre > 0 else 0,
                'max_pct': (float(row['最高']) - pre) / pre * 100 if pre > 0 else 0,
                'amount': float(row['成交额']) if row['成交额'] else 0,
                'vol': float(row['成交量']),
                'mkt_cap': float(row['总市值']) if row['总市值'] else 0
            }
        return res
    except:
        return {}


def monitor_loop(pool):
    raw_codes = [p['code'] for p in pool]
    real_time = fetch_akshare_realtime(raw_codes)
    active_pool = []

    for item in pool:
        code = item['code']
        if code in real_time:
            data = real_time[code]
            new_item = item.copy()
            new_item.update(data)

            # 注入历史数据
            hist = HISTORY_CACHE.get(code, {'yest_amt': 0, 'yest_auc_amt': 0, 'prev_amt': 0})
            new_item['history'] = hist

            # 优先用录制的竞价金额
            cached_auc = AUCTION_CACHE.get(code, 0)
            if cached_auc > 0:
                new_item['today_auction_amt'] = cached_auc
            else:
                new_item['today_auction_amt'] = data['amount']

            new_item['decision'] = get_smart_decision(new_item)
            active_pool.append(new_item)

    active_pool.sort(key=lambda x: x['pct'], reverse=True)

    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 170)
    print(f"🔥 F佬资金透视镜 v4.3 (修复版) | 核心监控: 竞价金额 | 单位: 亿元")
    print("=" * 170)
    print(
        f"{'名称':<8} {'市值':<8} {'现价':<7} {'涨幅':<9} {'今开%':<7} {'今竞(亿)':<10} {'昨额(亿)':<10} {'占比':<8} {'昨竞(亿)':<10} {'AI决策'}")
    print("-" * 170)

    for p in active_pool:
        name = p.get('name', '-')[:4]
        mkt_cap_yi = p['mkt_cap'] / 100000000

        t_auc_yi = p.get('today_auction_amt', 0) / 100000000
        y_amt_yi = p['history']['yest_amt'] / 100000000
        y_auc_yi = p['history']['yest_auc_amt'] / 100000000

        ratio = p.get('amt_ratio', 0)

        pct_color = Fore.RED if p['pct'] > 0 else Fore.GREEN
        if p['pct'] > 9.8: pct_color = Back.RED + Fore.WHITE

        ratio_str = f"{ratio:.1f}%"
        if p['open_pct'] > 2.0 and ratio < 8.0:
            ratio_str = f"{Fore.GREEN}{ratio_str}{Style.RESET_ALL}"
        elif ratio >= 10.0:
            ratio_str = f"{Fore.RED}{Style.BRIGHT}{ratio_str}{Style.RESET_ALL}"
        elif ratio >= 8.0:
            ratio_str = f"{Fore.RED}{ratio_str}{Style.RESET_ALL}"

        print(
            f"{name:<8} {mkt_cap_yi:<8.2f} {p['curr_p']:<7} {pct_color}{p['pct']:+.2f}%{Style.RESET_ALL:<9} {p['open_pct']:<7.1f} {t_auc_yi:<10.2f} {y_amt_yi:<10.2f} {ratio_str:<8} {y_auc_yi:<10.2f} {p['decision']}")

    print("=" * 170)


if __name__ == "__main__":
    concept_db = load_concept_db()
    pool = load_strategy_pool(concept_db)
    preload_history_data(pool)
    backfill_missing_today_auction(pool)

    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    if "09:15:00" < now_str < "09:30:05":
        mode_auction_capture(pool)

    try:
        while True:
            monitor_loop(pool)
            time.sleep(3)
    except KeyboardInterrupt:
        pass