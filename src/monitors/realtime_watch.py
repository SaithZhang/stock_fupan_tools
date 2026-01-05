# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py)
# v5.3 混合动力版 (优先读取同花顺本地导出数据 + API兜底)
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

# 📌 你的同花顺数据文件路径 (请确保文件存在，编码通常是 UTF-8 或 GBK)
THS_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_all_data.txt')

# 全局变量
AUCTION_CACHE = {}  # 今日竞价金额缓存
HISTORY_CACHE = {}  # 历史数据缓存
LOCAL_DATA_MAP = {}  # 本地同花顺数据缓存


# ================= 🛠️ 本地数据解析 (新增核心) =================

def clean_unit(val):
    """清洗单位: 1.5亿 -> 150000000"""
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
    """读取并解析同花顺导出数据"""
    global LOCAL_DATA_MAP
    if not os.path.exists(THS_DATA_PATH):
        print(f"{Fore.YELLOW}⚠️ 未找到本地数据文件: {THS_DATA_PATH}，将完全依赖API。{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}正在读取本地同花顺数据...{Style.RESET_ALL}")
    try:
        # 尝试读取，处理可能的编码问题
        try:
            with open(THS_DATA_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(THS_DATA_PATH, 'r', encoding='gbk') as f:
                content = f.read()

        # 解析逻辑 (复用离线脚本的智能匹配)
        lines = [re.split(r'\s+', line.strip()) for line in content.strip().split('\n') if line.strip()]
        if len(lines) < 2: return

        headers = lines[0]
        data_rows = lines[1:]

        # 映射列索引
        col_idx = {}
        yest_amt_idx = -1
        yest_date_int = 99999999

        for i, h in enumerate(headers):
            if '代码' in h:
                col_idx['code'] = i
            elif '名称' in h:
                col_idx['name'] = i
            elif '竞价涨幅' in h:
                col_idx['open_pct'] = i
            elif '竞价金额' in h:
                col_idx['auc_amt'] = i
            elif '流通市值' in h:
                col_idx['circ_mv'] = i
            elif '现价' in h:
                col_idx['curr_p'] = i
            elif '涨幅' in h and '竞价' not in h:
                col_idx['pct'] = i
            # 智能识别昨日成交额
            elif '成交额' in h:
                date_match = re.search(r'\d+', h)
                if date_match:
                    d = int(date_match.group())
                    # 找日期最小的那个成交额作为昨日/前日参考
                    if d < yest_date_int:
                        yest_date_int = d
                        yest_amt_idx = i

        # 填充数据
        count = 0
        for row in data_rows:
            if len(row) != len(headers): continue  # 跳过格式错误的行
            try:
                # 兼容代码格式 (SZ300500 -> 300500)
                raw_code = row[col_idx.get('code', 0)]
                code = re.sub(r'\D', '', raw_code)

                item = {
                    'name': row[col_idx.get('name', 1)],
                    'open_pct': clean_unit(row[col_idx.get('open_pct')]),
                    'today_auc_amt': clean_unit(row[col_idx.get('auc_amt')]),
                    'circ_mv': clean_unit(row[col_idx.get('circ_mv')]),
                    'curr_p': clean_unit(row[col_idx.get('curr_p')]),
                    'pct': clean_unit(row[col_idx.get('pct')]),
                }
                if yest_amt_idx != -1:
                    item['yest_amt'] = clean_unit(row[yest_amt_idx])

                LOCAL_DATA_MAP[code] = item
                count += 1
            except:
                continue

        print(f"{Fore.GREEN}✅ 成功加载 {count} 条本地数据! 历史回填将优先使用此数据。{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}❌ 读取本地数据失败: {e}{Style.RESET_ALL}")


# ================= 🛠️ 历史数据预加载 (混合模式) =================

def fetch_single_stock_history(code):
    """
    获取历史/竞价数据。
    [优先级] 本地文件 > 硬盘缓存 > API网络请求
    """
    res = {'yest_amt': 0, 'prev_amt': 0, 'yest_auc_amt': 0, 'today_auc_amt_fix': 0}

    # --- 1. 尝试从本地同花顺数据获取 (最快) ---
    if code in LOCAL_DATA_MAP:
        local = LOCAL_DATA_MAP[code]
        # 直接从本地数据拿昨日成交额
        if local.get('yest_amt', 0) > 0:
            res['yest_amt'] = local['yest_amt']

        # 直接从本地数据拿今日竞价 (作为复盘修复)
        if local.get('today_auc_amt', 0) > 0:
            res['today_auc_amt_fix'] = local['today_auc_amt']

        # 注意: 同花顺导出通常不含“昨日竞价”和“前日成交”，
        # 如果策略必须用到 ratios_prev (2进3)，还是需要 API 辅助。
        # 如果是 1进2，下面的 API 就可以跳过了。

    # --- 2. 如果关键数据缺失，才去调用 API (AkShare) ---
    # 比如我们缺 yest_amt 或者想算 2进3 的昨日竞价增量
    need_api = False
    if res['yest_amt'] == 0: need_api = True  # 本地没读到昨日成交
    # if 策略需要昨日竞价: need_api = True (如果你想省时间，可以把这行注释掉，只做1进2就不需要昨竞价)

    if need_api:
        try:
            # (这里保持原有的 API 逻辑不变，作为兜底)
            df_daily = ak.stock_zh_a_hist(symbol=code, period="daily",
                                          start_date=(datetime.datetime.now() - datetime.timedelta(days=10)).strftime(
                                              "%Y%m%d"),
                                          adjust="")
            if not df_daily.empty:
                df_daily = df_daily.sort_values(by='日期', ascending=False)
                today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                if df_daily.iloc[0]['日期'] == today_str:
                    if len(df_daily) >= 2: res['yest_amt'] = float(df_daily.iloc[1]['成交额'])
                else:
                    if len(df_daily) >= 1: res['yest_amt'] = float(df_daily.iloc[0]['成交额'])

            # 分钟线抓昨日竞价
            df_min = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
            if not df_min.empty:
                df_min['time_only'] = df_min['时间'].apply(lambda x: str(x).split(' ')[1])
                df_open = df_min[df_min['time_only'] == '09:30:00'].sort_values(by='时间', ascending=False)
                today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                for _, row in df_open.iterrows():
                    row_date = str(row['时间']).split(' ')[0]
                    if row_date == today_str:
                        # 如果本地没数据，才用 API 的分时补救
                        if res['today_auc_amt_fix'] == 0:
                            res['today_auc_amt_fix'] = float(row['成交额'])
                    elif row_date < today_str:
                        res['yest_auc_amt'] = float(row['成交额'])
                        break
        except:
            pass

    return code, res


def preload_history_data(pool):
    print(f"{Fore.CYAN}正在匹配数据 (本地 + API兜底)...{Style.RESET_ALL}")
    codes = [p['code'] for p in pool]

    # 如果本地数据已经很全了，减少线程数或者不用线程，直接内存匹配会更快
    # 但为了兼容 API 兜底，还是保留线程池
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_stock_history, code): code for code in codes}
        c = 0
        for future in as_completed(futures):
            c += 1
            code, data = future.result()
            HISTORY_CACHE[code] = data
            # 进度条效果
            if code in LOCAL_DATA_MAP:
                print(f"\r进度: {c}/{len(codes)} [本地命中]", end="")
            else:
                print(f"\r进度: {c}/{len(codes)} [API获取]", end="")
    print(f"\n{Fore.GREEN}✅ 数据准备完毕{Style.RESET_ALL}")


# ================= 🛠️ 竞价录制与基础 =================

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
    while True:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if now_str > "09:30:05": break
        codes = [p['code'] for p in pool]
        df = ak.stock_zh_a_spot_em()
        if not df.empty:
            df = df[df['代码'].isin(codes)]
            auc = {str(r['代码']): float(r['成交额']) for _, r in df.iterrows() if r['成交额'] > 0}
            save_auction_to_disk(auc)
            print(f"\r[{now_str}] 已录入 {len(auc)} 只标的", end="")
        time.sleep(3)


# ================= 🧠 核心策略逻辑 (v5.2 防坑版) =================

def parse_board_stage(tag):
    if not tag: return 1
    if "1进2" in tag or "1板" in tag: return 1
    if "2进3" in tag or "2板" in tag: return 2
    if "3进4" in tag or "3板" in tag: return 3
    if "4进5" in tag or "4板" in tag: return 4
    return 1


def get_strict_decision(item):
    # 1. 基础数据
    code = item['code']
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

    # --- 基础清洗 ---
    if open_pct > 9.8: return f"{Fore.CYAN}一字板{Style.RESET_ALL}", 0
    if open_pct < -2.0: return f"低开({open_pct}%)", 0

    min_open_pct = 1.8
    if circ_mv > 20_0000_0000: min_open_pct = 3.0
    if stage == 1: min_open_pct = 3.7

    if open_pct < min_open_pct:
        return f"弱竞价({open_pct}%)", 0

    # --- 1进2 核心规则 ---
    if stage == 1:
        if ratio_auc_total < 3.0: return f"量能不足({ratio_auc_total:.1f}%)", 0
        if ratio_auc_total > 18.0: return f"过热({ratio_auc_total:.1f}%)", 0

    # --- 规则 5: 及格线判定 ---
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

    if not is_qualified:
        return f"{Fore.YELLOW}观察:{fail_reason}{Style.RESET_ALL}", 40

    # 🔥 完美门槛：竞/流必须显著大于及格线 (1.5倍以上)
    strict_perfect_line = 1.5

    if stage == 1 and open_pct > 5.0 and 5.0 <= ratio_auc_total <= 15.0:
        if ratio_auc_circ >= strict_perfect_line:
            return f"{Back.RED}{Fore.WHITE} 🔥 完美1进2 {Style.RESET_ALL}", 95
        else:
            return f"{Fore.RED}★ 达标关注(弱强){Style.RESET_ALL}", 75

    return f"{Fore.RED}★ 达标关注{Style.RESET_ALL}", 70


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


def fetch_realtime_data(pool):
    # 如果本地有数据，优先用本地数据模拟“实时”
    # 这对盘后复盘非常有用，避免了调 API 拿到收盘价
    if LOCAL_DATA_MAP:
        res = {}
        for p in pool:
            code = p['code']
            if code in LOCAL_DATA_MAP:
                local = LOCAL_DATA_MAP[code]
                res[code] = {
                    'pct': local['pct'],
                    'open_p': 0,  # 复盘一般不看这个，看 open_pct
                    'curr_p': local['curr_p'],
                    'pre_close': 0,
                    'amount': 0,  # 盘中成交额，复盘时用不到，用到的是 today_auc_amt
                    'circ_mv': local['circ_mv'],
                    'open_pct': local['open_pct']  # 直接用本地的竞价涨幅
                }
        if res: return res

    # 否则走 API
    codes = [p['code'] for p in pool]
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
    realtime = fetch_realtime_data(pool)
    display_list = []

    today_auc_cache = load_auction_from_disk()
    now_time = datetime.datetime.now().strftime("%H:%M")
    is_live_auction = "09:15" <= now_time <= "09:30"

    for item in pool:
        code = item['code']
        if code not in realtime: continue

        data = realtime[code]
        full_item = {**item, **data}

        hist = HISTORY_CACHE.get(code, {})
        full_item['history'] = hist

        # --- 竞价数据来源选择 ---
        if code in today_auc_cache:
            full_item['today_auction_amt'] = today_auc_cache[code]
        elif is_live_auction:
            full_item['today_auction_amt'] = data['amount']
        # 优先用本地同花顺数据作为“今日竞价”
        elif hist.get('today_auc_amt_fix', 0) > 0:
            full_item['today_auction_amt'] = hist['today_auc_amt_fix']
        else:
            full_item['today_auction_amt'] = 0

        decision_str, score = get_strict_decision(full_item)
        full_item['decision'] = decision_str
        full_item['score'] = score

        display_list.append(full_item)

    display_list.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    os.system('cls' if os.name == 'nt' else 'clear')
    print(
        f"{Back.BLUE}{Fore.WHITE} F佬 · 监管加强版竞价监控 v5.3 (本地数据优先) {Style.RESET_ALL} | {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 140)
    print(
        f"{'代码':<7} {'名称':<8} {'现价':<7} {'竞价%':<7} {'现涨%':<7} {'竞价额(亿)':<11} {'竞/流%':<8} {'竞/昨%':<8} {'AI决策'}")
    print("-" * 140)

    for p in display_list:
        auc_yi = p.get('today_auction_amt', 0) / 100000000
        c_open = Fore.RED if p['open_pct'] > 0 else Fore.GREEN

        # 高亮
        r_circ_str = f"{p.get('r_circ', 0):.2f}"
        if p.get('r_circ', 0) > 1.5: r_circ_str = f"{Fore.MAGENTA}{r_circ_str}{Style.RESET_ALL}"

        r_total_str = f"{p.get('r_total', 0):.1f}"
        if 5 <= p.get('r_total', 0) <= 18: r_total_str = f"{Fore.RED}{r_total_str}{Style.RESET_ALL}"

        print(
            f"{p['code']:<7} {p.get('name', '-')[:4]:<8} {p['curr_p']:<7} {c_open}{p['open_pct']:<7.2f}{Style.RESET_ALL} {p['pct']:<7.2f} {auc_yi:<11.2f} {r_circ_str:<8} {r_total_str:<8} {p['decision']}")
    print("=" * 140)
    print(f"注: 完美1进2需满足: 竞/昨% 3~18% 且 竞/流% > 1.5% (严格版)")


if __name__ == "__main__":
    # 0. 加载本地同花顺数据
    load_local_ths_data()

    # 1. 加载池子
    pool = load_strategy_pool()
    backfill_data = AUCTION_CACHE.update(load_auction_from_disk())

    # 2. 预加载历史 (现在会优先匹配本地数据)
    preload_history_data(pool)

    # 3. 监控
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    if "09:15:00" < now_str < "09:30:05":
        mode_auction_capture(pool)

    try:
        while True:
            monitor_loop(pool)
            time.sleep(3)
    except KeyboardInterrupt:
        pass