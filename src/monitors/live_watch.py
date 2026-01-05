# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src/monitors/live_watch.py)
# v8.0 极速本地版 (Local First Speed Edition)
# 核心逻辑：
#   1. 9:25前：读取本地TXT (含连板数/昨日额/市值) + 仅API补充昨日竞价数据。
#   2. 9:25后：只拉取实时 [竞价金额] 和 [开盘涨幅]，其余全本地算。
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
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

# 📌 同花顺导出数据路径 (必须包含: 代码, 名称, 连板数, 流通市值, 昨成交 等)
THS_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_all_data.txt')

# 全局内存变量
AUCTION_CACHE = {}  # 今日竞价金额缓存
HISTORY_CACHE = {}  # 历史数据 (昨日竞价/昨日成交)
LOCAL_DATA_MAP = {}  # 本地同花顺数据缓存 (核心数据库)


# ================= 🛠️ 1. 智能本地数据解析 (支持连板数) =================

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


def load_local_ths_data():
    """
    读取同花顺数据，智能识别 [连板数] 列
    """
    global LOCAL_DATA_MAP
    if not os.path.exists(THS_DATA_PATH):
        print(f"{Fore.YELLOW}⚠️ 未找到本地数据 {THS_DATA_PATH}，将降级为全API模式。{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}正在读取本地同花顺数据 (连板/市值/昨日额)...{Style.RESET_ALL}")
    try:
        try:
            with open(THS_DATA_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(THS_DATA_PATH, 'r', encoding='gbk') as f:
                content = f.read()

        lines = [re.split(r'\s+', line.strip()) for line in content.strip().split('\n') if line.strip()]
        if len(lines) < 2: return

        headers = lines[0]
        data_rows = lines[1:]

        col_idx = {}
        yest_amt_idx = -1
        yest_date_int = 99999999

        # --- 智能列名映射 ---
        for i, h in enumerate(headers):
            if '代码' in h:
                col_idx['code'] = i
            elif '名称' in h:
                col_idx['name'] = i
            elif '竞价涨幅' in h:
                col_idx['open_pct'] = i  # 用于复盘
            elif '竞价金额' in h:
                col_idx['auc_amt'] = i  # 用于复盘
            elif '流通市值' in h:
                col_idx['circ_mv'] = i
            elif '现价' in h:
                col_idx['curr_p'] = i
            # 识别连板数 (常见的列名变种)
            elif '连板' in h or '几板' in h or '涨停统计' in h:
                col_idx['boards'] = i
            # 识别昨日成交额 (找日期最小的成交额列)
            elif '成交额' in h:
                date_match = re.search(r'\d+', h)
                if date_match:
                    d = int(date_match.group())
                    if d < yest_date_int:
                        yest_date_int = d
                        yest_amt_idx = i
                elif '昨日' in h or '昨' in h:  # 显式“昨成交”
                    yest_amt_idx = i

        count = 0
        for row in data_rows:
            if len(row) != len(headers): continue
            try:
                raw_code = row[col_idx.get('code', 0)]
                code = re.sub(r'\D', '', raw_code)

                # 基础字段
                item = {
                    'name': row[col_idx.get('name', 1)],
                    'circ_mv': clean_unit(row[col_idx.get('circ_mv')]),
                    'curr_p': clean_unit(row[col_idx.get('curr_p')]),
                }

                # 提取连板数 (如果没有则默认为0)
                if 'boards' in col_idx:
                    val = row[col_idx['boards']]
                    # 处理 "3天2板" 这种格式，或者纯数字 "3"
                    if '板' in str(val):
                        # 提取 '2板' 中的 2
                        b_match = re.search(r'(\d+)板', str(val))
                        item['boards'] = int(b_match.group(1)) if b_match else 0
                    else:
                        item['boards'] = int(clean_unit(val))
                else:
                    item['boards'] = 0

                # 提取昨日成交额
                if yest_amt_idx != -1:
                    item['yest_amt'] = clean_unit(row[yest_amt_idx])

                # 提取复盘用的竞价数据 (可选)
                if 'auc_amt' in col_idx: item['today_auc_amt_fix'] = clean_unit(row[col_idx['auc_amt']])

                LOCAL_DATA_MAP[code] = item
                count += 1
            except:
                continue
        print(f"{Fore.GREEN}✅ 本地数据加载成功: {count} 条 | 已包含连板字段{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 本地数据读取跳过: {e}{Style.RESET_ALL}")


# ================= 🛠️ 2. 极简历史数据预加载 =================

def calculate_boards_fallback(df):
    """(备用) 仅当本地没有连板数据时，才用API算"""
    if df.empty: return 0
    boards = 0
    for index, row in df.iterrows():
        code = str(row['股票代码'])
        pct = float(row['涨跌幅'])
        threshold = 19.5 if code.startswith(('30', '68')) else 9.5
        if pct >= threshold:
            boards += 1
        else:
            break
    return boards


def fetch_single_stock_history(code):
    """
    预加载逻辑：
    1. 如果本地有 [连板] 和 [昨成交]，则【跳过】日线API，只拉取 [昨竞价]。
    2. 如果本地缺数据，则拉取日线API进行补充。
    """
    res = {'yest_amt': 0, 'yest_auc_amt': 0, 'yest_boards': 0}

    # 检查本地数据
    local = LOCAL_DATA_MAP.get(code, {})
    has_local_boards = 'boards' in local
    has_local_amt = 'yest_amt' in local and local['yest_amt'] > 0

    # --- 1. 获取基础数据 (日线级别) ---
    if has_local_boards and has_local_amt:
        # ✅ 命中本地缓存，跳过繁重的日线API
        res['yest_boards'] = local['boards']
        res['yest_amt'] = local['yest_amt']
    else:
        # ❌ 本地缺失，不得不调用API
        try:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=40)).strftime("%Y%m%d")
            df_daily = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, adjust="")
            if not df_daily.empty:
                df_daily = df_daily.sort_values(by='日期', ascending=False)
                if str(df_daily.iloc[0]['日期']) == datetime.datetime.now().strftime('%Y-%m-%d'):
                    df_daily = df_daily.iloc[1:]

                res['yest_boards'] = calculate_boards_fallback(df_daily)
                if len(df_daily) >= 1: res['yest_amt'] = float(df_daily.iloc[0]['成交额'])
        except:
            pass

    # --- 2. 获取昨日竞价 (API 必须) ---
    # 同花顺导出通常不含“昨日9:30成交额”，这部分目前只能靠API补
    # 如果策略里 2进3 必须看昨竞价增量，则不能省；如果是1进2其实可以省。
    # 这里为了通用性，保留获取，因为是分钟线，数据量小。
    try:
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
    print(f"{Fore.CYAN}正在预处理数据 (本地优先 + 最小化API)...{Style.RESET_ALL}")
    codes = [p['code'] for p in pool]
    # 线程池
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_stock_history, code): code for code in codes}
        c = 0
        for future in as_completed(futures):
            c += 1
            code, data = future.result()
            HISTORY_CACHE[code] = data

            # 显示优化：如果是本地命中的，打个标记
            src = "API"
            if code in LOCAL_DATA_MAP and 'boards' in LOCAL_DATA_MAP[code]:
                src = "Local"
            print(f"\r进度: {c}/{len(codes)} [{src}]", end="")
    print(f"\n{Fore.GREEN}✅ 准备就绪，静待9:25竞价数据{Style.RESET_ALL}")


# ================= 🛠️ 3. 竞价录制 (保持不变) =================

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
    print(f"{Back.MAGENTA}{Fore.WHITE} 🎥 9:15-9:25 竞价数据捕获中... {Style.RESET_ALL}")
    while True:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if now_str > "09:30:05":
            print("\n⏰ 竞价结束，开始决策...")
            break
        codes = [p['code'] for p in pool]
        try:
            df = ak.stock_zh_a_spot_em()
            if not df.empty:
                df = df[df['代码'].isin(codes)]
                auc = {str(r['代码']): float(r['成交额']) for _, r in df.iterrows() if r['成交额'] > 0}
                save_auction_to_disk(auc)
                print(f"\r[{now_str}] 已捕获 {len(auc)} 只标的竞价", end="")
        except:
            pass
        time.sleep(3)


# ================= 🧠 4. 决策逻辑 (严格版) =================

def parse_board_stage(tag):
    if not tag: return 1
    if "1进2" in tag or "1板" in tag: return 1
    if "2进3" in tag or "2板" in tag: return 2
    if "3进4" in tag or "3板" in tag: return 3
    return 1


def get_strict_decision(item):
    open_pct = item['open_pct']
    auc_amt = item.get('today_auction_amt', 0)

    # 核心分母：优先用本地读取的市值和昨成交
    circ_mv = item.get('circ_mv', 0)
    yest_amt = item['history'].get('yest_amt', 0)
    yest_auc = item['history'].get('yest_auc_amt', 0)

    tag = item.get('tag_display', '')
    stage = parse_board_stage(tag)

    # 关键比率计算
    ratio_auc_total = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0
    ratio_auc_circ = (auc_amt / circ_mv * 100) if circ_mv > 0 else 0
    ratio_auc_prev = (auc_amt / yest_auc) if yest_auc > 0 else 0

    item['r_total'] = ratio_auc_total
    item['r_circ'] = ratio_auc_circ
    item['r_prev'] = ratio_auc_prev

    # --- 决策树 ---
    if open_pct > 9.8: return f"{Fore.CYAN}一字板{Style.RESET_ALL}", 0
    if open_pct < -2.0: return f"低开({open_pct}%)", 0

    # 门槛
    min_open = 3.0 if circ_mv > 20_0000_0000 else 1.8
    if stage == 1: min_open = 3.7
    if open_pct < min_open: return f"弱竞价({open_pct}%)", 0

    is_qualified = False
    fail_reason = ""

    # 1进2 重点看 竞/昨 和 竞/流
    if stage == 1:
        if ratio_auc_total < 3.0: return f"量能不足({ratio_auc_total:.1f}%)", 0
        if ratio_auc_total > 18.0: return f"过热({ratio_auc_total:.1f}%)", 0

        limit_circ = 0.82 if circ_mv >= 27_0000_0000 else 0.78
        if ratio_auc_circ > limit_circ:
            is_qualified = True
        else:
            fail_reason = f"量不足({ratio_auc_circ:.2f}%)"

    # 连板 重点看 竞价增量 (竞今/竞昨)
    else:
        if ratio_auc_prev > 1.3:
            is_qualified = True
        else:
            fail_reason = f"增量差({ratio_auc_prev:.1f})"

    if not is_qualified: return f"{Fore.YELLOW}观察:{fail_reason}{Style.RESET_ALL}", 40

    # 🔥 完美信号
    if stage == 1 and open_pct > 5.0 and 5.0 <= ratio_auc_total <= 15.0 and ratio_auc_circ >= 1.5:
        return f"{Back.RED}{Fore.WHITE} 🔥 完美1进2 {Style.RESET_ALL}", 95

    return f"{Fore.RED}★ 达标关注{Style.RESET_ALL}", 70


# ================= 🛠️ 5. 极速监控循环 =================

def load_strategy_pool():
    df = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, dtype={'code': str})
        except:
            pass
    if df.empty: return []
    return df.to_dict('records')


def fetch_live_snapshot(pool):
    """
    只拉取 [代码, 涨跌幅, 今开, 现价, 成交额]
    这里只为了获取 9:25 出来后的 amount 和 open_pct
    """
    codes = [p['code'] for p in pool]
    try:
        df = ak.stock_zh_a_spot_em()
        df = df[df['代码'].isin(codes)]
        res = {}
        for _, row in df.iterrows():
            code = row['代码']
            item = {
                'pct': float(row['涨跌幅']),
                'open_p': float(row['今开']),
                'curr_p': float(row['最新价']),
                'amount': float(row['成交额']),  # 这是实时的总成交额(9:25时即为竞价额)
                'pre_close': float(row['昨收'])
            }
            # 计算开盘涨幅
            if item['pre_close'] > 0:
                item['open_pct'] = (item['open_p'] - item['pre_close']) / item['pre_close'] * 100
            else:
                item['open_pct'] = 0
            res[code] = item
        return res
    except:
        return {}


def monitor_loop(pool):
    # 1. 唯一的网络请求：获取最新的一行数据
    live_data = fetch_live_snapshot(pool)
    display_list = []

    today_auc_cache = load_auction_from_disk()
    now_time = datetime.datetime.now().strftime("%H:%M")
    is_live_auction = "09:15" <= now_time <= "09:30"

    # --- 梯队统计 (纯本地计算) ---
    ladder_counts = {}
    for item in pool:
        code = item['code']
        # 优先用本地连板数，没有才用历史算出来的
        if code in LOCAL_DATA_MAP and 'boards' in LOCAL_DATA_MAP[code]:
            b_num = LOCAL_DATA_MAP[code]['boards']
        else:
            b_num = HISTORY_CACHE.get(code, {}).get('yest_boards', 0)

        if b_num >= 2: ladder_counts[b_num] = ladder_counts.get(b_num, 0) + 1
    # ---------------------------

    for item in pool:
        code = item['code']
        if code not in live_data: continue  # 没取到实时数据就跳过

        # 组装数据：本地(市值/昨额) + 实时(涨幅/现额)
        snapshot = live_data[code]
        full_item = item.copy()

        # 注入实时数据
        full_item['open_pct'] = snapshot['open_pct']
        full_item['pct'] = snapshot['pct']
        full_item['curr_p'] = snapshot['curr_p']

        # 注入本地/历史基础数据
        if code in LOCAL_DATA_MAP:
            local = LOCAL_DATA_MAP[code]
            full_item['circ_mv'] = local.get('circ_mv', 0)
            full_item['name'] = local.get('name', item.get('name'))
            # 昨成交额：本地优先
            if local.get('yest_amt', 0) > 0:
                full_item['history'] = {'yest_amt': local['yest_amt']}
            else:
                full_item['history'] = HISTORY_CACHE.get(code, {})

            # 连板数：本地优先
            if 'boards' in local:
                full_item['boards_val'] = local['boards']
            else:
                full_item['boards_val'] = HISTORY_CACHE.get(code, {}).get('yest_boards', 0)
        else:
            full_item['history'] = HISTORY_CACHE.get(code, {})
            full_item['circ_mv'] = full_item['history'].get('circ_mv', 0)  # 这是一个兜底，通常history里没有mv
            full_item['boards_val'] = full_item['history'].get('yest_boards', 0)

        # 补齐昨竞价 (这个必须来自History)
        full_item['history']['yest_auc_amt'] = HISTORY_CACHE.get(code, {}).get('yest_auc_amt', 0)

        # 确定今日竞价金额
        if code in today_auc_cache:
            full_item['today_auction_amt'] = today_auc_cache[code]
        elif is_live_auction:
            full_item['today_auction_amt'] = snapshot['amount']
        elif code in LOCAL_DATA_MAP and 'today_auc_amt_fix' in LOCAL_DATA_MAP[code]:
            # 复盘用
            full_item['today_auction_amt'] = LOCAL_DATA_MAP[code]['today_auc_amt_fix']
        else:
            full_item['today_auction_amt'] = 0

        # --- 身位展示逻辑 ---
        b_num = full_item['boards_val']
        is_unique = (b_num >= 3 and ladder_counts.get(b_num, 0) == 1)

        board_str = f"{b_num}B"
        if snapshot['pct'] > 9.8: board_str = f"{b_num + 1}B"
        if is_unique: board_str += "👑"
        full_item['board_info'] = board_str
        # ------------------

        decision_str, score = get_strict_decision(full_item)
        full_item['decision'] = decision_str
        full_item['score'] = score
        display_list.append(full_item)

    display_list.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    os.system('cls' if os.name == 'nt' else 'clear')
    print(
        f"{Back.RED}{Fore.WHITE} 🔥 F佬 · 极速决策系统 v8.0 (Local First) {Style.RESET_ALL} | {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 155)
    print(
        f"{'代码':<7} {'名称':<8} {'现价':<7} {'竞价%':<7} {'现涨%':<7} {'身位':<6} {'竞价额(亿)':<11} {'竞/流%':<8} {'竞/昨%':<8} {'AI决策'}")
    print("-" * 155)

    for p in display_list:
        auc_yi = p.get('today_auction_amt', 0) / 100000000
        c_open = Fore.RED if p['open_pct'] > 0 else Fore.GREEN

        r_circ_str = f"{p.get('r_circ', 0):.2f}"
        if p.get('r_circ', 0) > 1.5: r_circ_str = f"{Fore.MAGENTA}{r_circ_str}{Style.RESET_ALL}"

        r_total_str = f"{p.get('r_total', 0):.1f}"
        if 5 <= p.get('r_total', 0) <= 18: r_total_str = f"{Fore.RED}{r_total_str}{Style.RESET_ALL}"

        print(
            f"{p['code']:<7} {p.get('name', '-')[:4]:<8} {p['curr_p']:<7} {c_open}{p['open_pct']:<7.2f}{Style.RESET_ALL} {p['pct']:<7.2f} {p['board_info']:<6} {auc_yi:<11.2f} {r_circ_str:<8} {r_total_str:<8} {p['decision']}")
    print("=" * 155)
    print(f"注: 👑 唯一身位 | 数据源: {'本地+实时' if LOCAL_DATA_MAP else '纯网络'}")


if __name__ == "__main__":
    # 1. 加载本地同花顺数据 (核心)
    load_local_ths_data()

    # 2. 加载策略池
    pool = load_strategy_pool()
    backfill_data = AUCTION_CACHE.update(load_auction_from_disk())

    # 3. 预加载 (根据本地数据情况，智能决定是否跳过API)
    preload_history_data(pool)

    # 4. 竞价录制 (9:15-9:25)
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    if "09:15:00" < now_str < "09:30:05":
        mode_auction_capture(pool)

    # 5. 极速循环
    try:
        while True:
            monitor_loop(pool)
            time.sleep(1.5)  # 加快刷新频率，因为计算开销变小了
    except KeyboardInterrupt:
        pass