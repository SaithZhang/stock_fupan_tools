# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/live_watch.py)
# v6.0 实盘专用版 (Pure Live) - 9:15启动，全联网，自动录制竞价
# ==============================================================================
import akshare as ak
import pandas as pd
import time
import os
import json
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style, Back

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

AUCTION_CACHE = {}
HISTORY_CACHE = {}


# ================= 🛠️ 核心策略逻辑 (需与复盘版保持一致) =================

def parse_board_stage(tag):
    if not tag: return 1
    if "1进2" in tag or "1板" in tag: return 1
    if "2进3" in tag or "2板" in tag: return 2
    if "3进4" in tag or "3板" in tag: return 3
    if "4进5" in tag or "4板" in tag: return 4
    return 1


def get_strict_decision(item):
    """v5.3 严格版策略"""
    open_pct = item['open_pct']
    auc_amt = item.get('today_auction_amt', 0)
    circ_mv = item.get('circ_mv', 0)
    yest_amt = item['history'].get('yest_amt', 0)
    yest_auc = item['history'].get('yest_auc_amt', 0)
    tag = item.get('tag_display', '')
    stage = parse_board_stage(tag)

    ratio_auc_total = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0
    ratio_auc_circ = (auc_amt / circ_mv * 100) if circ_mv > 0 else 0
    ratio_auc_prev = (auc_amt / yest_auc) if yest_auc > 0 else 0

    item['r_total'] = ratio_auc_total
    item['r_circ'] = ratio_auc_circ
    item['r_prev'] = ratio_auc_prev

    if open_pct > 9.8: return f"{Fore.CYAN}一字板{Style.RESET_ALL}", 0
    if open_pct < -2.0: return f"低开({open_pct}%)", 0

    min_open_pct = 1.8
    if circ_mv > 20_0000_0000: min_open_pct = 3.0
    if stage == 1: min_open_pct = 3.7

    if open_pct < min_open_pct: return f"弱竞价({open_pct}%)", 0

    if stage == 1:
        if ratio_auc_total < 3.0: return f"量能不足({ratio_auc_total:.1f}%)", 0
        if ratio_auc_total > 18.0: return f"过热({ratio_auc_total:.1f}%)", 0

    cap_type = "micro"
    if 20_0000_0000 <= circ_mv < 27_0000_0000:
        cap_type = "small"
    elif circ_mv >= 27_0000_0000:
        cap_type = "large"

    is_qualified = False
    fail_reason = ""
    limit_circ = 0.95
    if cap_type == "small":
        limit_circ = 0.78
    elif cap_type == "large":
        limit_circ = 0.82

    if stage == 1:
        if ratio_auc_circ > limit_circ:
            is_qualified = True
        else:
            fail_reason = f"1进2量不足({ratio_auc_circ:.2f}%)"
    else:
        if ratio_auc_prev > 1.3:
            is_qualified = True
        else:
            fail_reason = "连板增量不足"

    if not is_qualified: return f"{Fore.YELLOW}观察:{fail_reason}{Style.RESET_ALL}", 40

    # 🔥 完美门槛 > 1.5%
    strict_perfect_line = 1.5
    if stage == 1 and open_pct > 5.0 and 5.0 <= ratio_auc_total <= 15.0:
        if ratio_auc_circ >= strict_perfect_line:
            return f"{Back.RED}{Fore.WHITE} 🔥 完美1进2 {Style.RESET_ALL}", 95
        else:
            return f"{Fore.RED}★ 达标关注(弱强){Style.RESET_ALL}", 75

    return f"{Fore.RED}★ 达标关注{Style.RESET_ALL}", 70


# ================= 🛠️ API 数据交互 =================

def fetch_single_stock_history(code):
    res = {'yest_amt': 0, 'prev_amt': 0, 'yest_auc_amt': 0}
    try:
        # 获取昨日成交 (实盘必须保证这是准确的)
        df_daily = ak.stock_zh_a_hist(symbol=code, period="daily",
                                      start_date=(datetime.datetime.now() - datetime.timedelta(days=10)).strftime(
                                          "%Y%m%d"),
                                      adjust="")
        if not df_daily.empty:
            df_daily = df_daily.sort_values(by='日期', ascending=False)
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')

            # 盘中获取日线，第一条通常是昨天 (因为今天的还没收盘)
            # 但为了稳健，如果AKShare返回了今天(虽然不完整)，我们取下一条
            if str(df_daily.iloc[0]['日期']) == today_str:
                if len(df_daily) >= 2: res['yest_amt'] = float(df_daily.iloc[1]['成交额'])
            else:
                if len(df_daily) >= 1: res['yest_amt'] = float(df_daily.iloc[0]['成交额'])

        # 获取昨日竞价 (用于2进3判定)
        df_min = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
        if not df_min.empty:
            df_min['time_only'] = df_min['时间'].apply(lambda x: str(x).split(' ')[1])
            df_open = df_min[df_min['time_only'] == '09:30:00'].sort_values(by='时间', ascending=False)
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            for _, row in df_open.iterrows():
                row_date = str(row['时间']).split(' ')[0]
                if row_date < today_str:
                    res['yest_auc_amt'] = float(row['成交额'])
                    break
    except:
        pass
    return code, res


def preload_history_data(pool):
    print(f"{Fore.CYAN}正在初始化实盘数据 (联网获取昨日成交)...{Style.RESET_ALL}")
    codes = [p['code'] for p in pool]
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_stock_history, code): code for code in codes}
        c = 0
        for future in as_completed(futures):
            c += 1
            code, data = future.result()
            HISTORY_CACHE[code] = data
            print(f"\r进度: {c}/{len(codes)}", end="")
    print(f"\n{Fore.GREEN}✅ 实盘数据准备就绪{Style.RESET_ALL}")


# ================= 🛠️ 竞价录制 =================

def get_today_cache_path():
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    return os.path.join(CACHE_DIR, f"auction_amount_{today_str}.json")


def save_auction_to_disk(data_dict):
    try:
        path = get_today_cache_path()
        old = {}
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: old = json.load(f)
        old.update(data_dict)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(old, f)
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
    print(f"{Back.MAGENTA}{Fore.WHITE} 🎥 9:15-9:30 竞价录制模式 {Style.RESET_ALL}")
    print(f"请保持脚本运行，直到开盘...")
    while True:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if now_str > "09:30:05":
            print("\n⏰ 竞价结束，切换至实时监控...")
            break
        codes = [p['code'] for p in pool]
        try:
            df = ak.stock_zh_a_spot_em()
            if not df.empty:
                df = df[df['代码'].isin(codes)]
                auc = {str(r['代码']): float(r['成交额']) for _, r in df.iterrows() if r['成交额'] > 0}
                save_auction_to_disk(auc)
                print(f"\r[{now_str}] 已录入 {len(auc)} 只标的", end="")
        except:
            pass
        time.sleep(3)


# ================= 🛠️ 监控主循环 =================

def load_strategy_pool():
    df = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, dtype={'code': str})
        except:
            pass
    if df.empty: return []
    return df.to_dict('records')


def fetch_realtime_data(codes):
    try:
        df = ak.stock_zh_a_spot_em()
        df = df[df['代码'].isin(codes)]
        res = {}
        for _, row in df.iterrows():
            code = row['代码']
            res[code] = {
                'pct': float(row['涨跌幅']),
                'open_p': float(row['今开']),
                'curr_p': float(row['最新价']),
                'pre_close': float(row['昨收']),
                'amount': float(row['成交额']),
                'circ_mv': float(row['流通市值']) if row['流通市值'] else 0
            }
            if res[code]['pre_close'] > 0:
                res[code]['open_pct'] = (res[code]['open_p'] - res[code]['pre_close']) / res[code]['pre_close'] * 100
            else:
                res[code]['open_pct'] = 0
        return res
    except:
        return {}


def monitor_loop(pool):
    codes = [p['code'] for p in pool]
    realtime = fetch_realtime_data(codes)
    display_list = []

    today_auc_cache = load_auction_from_disk()
    now_time = datetime.datetime.now().strftime("%H:%M")
    is_live_auction = "09:15" <= now_time <= "09:30"

    for item in pool:
        code = item['code']
        if code not in realtime: continue

        data = realtime[code]
        full_item = {**item, **data}
        full_item['history'] = HISTORY_CACHE.get(code, {})

        # 竞价金额取值逻辑
        if code in today_auc_cache:
            full_item['today_auction_amt'] = today_auc_cache[code]
        elif is_live_auction:
            full_item['today_auction_amt'] = data['amount']
        else:
            full_item['today_auction_amt'] = 0  # 盘中无录制则失效

        decision_str, score = get_strict_decision(full_item)
        full_item['decision'] = decision_str
        full_item['score'] = score
        display_list.append(full_item)

    display_list.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    os.system('cls' if os.name == 'nt' else 'clear')
    print(
        f"{Back.RED}{Fore.WHITE} 🔥 F佬 · 实盘作战系统 v6.0 {Style.RESET_ALL} | {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 140)
    print(
        f"{'代码':<7} {'名称':<8} {'现价':<7} {'竞价%':<7} {'现涨%':<7} {'竞价额(亿)':<11} {'竞/流%':<8} {'竞/昨%':<8} {'AI决策'}")
    print("-" * 140)

    for p in display_list:
        auc_yi = p.get('today_auction_amt', 0) / 100000000
        c_open = Fore.RED if p['open_pct'] > 0 else Fore.GREEN
        r_circ_str = f"{p.get('r_circ', 0):.2f}"
        if p.get('r_circ', 0) > 1.5: r_circ_str = f"{Fore.MAGENTA}{r_circ_str}{Style.RESET_ALL}"
        r_total_str = f"{p.get('r_total', 0):.1f}"
        if 5 <= p.get('r_total', 0) <= 18: r_total_str = f"{Fore.RED}{r_total_str}{Style.RESET_ALL}"

        print(
            f"{p['code']:<7} {p.get('name', '-')[:4]:<8} {p['curr_p']:<7} {c_open}{p['open_pct']:<7.2f}{Style.RESET_ALL} {p['pct']:<7.2f} {auc_yi:<11.2f} {r_circ_str:<8} {r_total_str:<8} {p['decision']}")
    print("=" * 140)


if __name__ == "__main__":
    pool = load_strategy_pool()
    backfill_data = AUCTION_CACHE.update(load_auction_from_disk())
    preload_history_data(pool)

    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    if "09:15:00" < now_str < "09:30:05":
        mode_auction_capture(pool)

    try:
        while True:
            monitor_loop(pool)
            time.sleep(3)
    except KeyboardInterrupt:
        pass