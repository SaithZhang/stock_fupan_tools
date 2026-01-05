# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/daily_fupan.py)
# v6.0 盘后复盘专用版 (Offline Review) - 读取同花顺数据
# ==============================================================================
import pandas as pd
import os
import re
import sys
import datetime
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
THS_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_all_data.txt')


# ================= 🛠️ 核心策略逻辑 (需与实盘版保持一致) =================

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
    yest_amt = item.get('yest_amt', 0)
    yest_auc = item.get('yest_auc_amt', 0)
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


# ================= 🛠️ 本地数据读取 =================

def clean_unit(val):
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
    if not os.path.exists(THS_DATA_PATH):
        print(f"{Fore.RED}⚠️ 错误: 未找到 {THS_DATA_PATH}{Style.RESET_ALL}")
        return {}

    print(f"{Fore.CYAN}正在解析同花顺本地数据...{Style.RESET_ALL}")
    data_map = {}
    try:
        try:
            with open(THS_DATA_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(THS_DATA_PATH, 'r', encoding='gbk') as f:
                content = f.read()

        lines = [re.split(r'\s+', line.strip()) for line in content.strip().split('\n') if line.strip()]
        if len(lines) < 2: return {}

        headers = lines[0]
        data_rows = lines[1:]

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
            elif '成交额' in h:
                date_match = re.search(r'\d+', h)
                if date_match:
                    d = int(date_match.group())
                    if d < yest_date_int:
                        yest_date_int = d
                        yest_amt_idx = i

        count = 0
        for row in data_rows:
            if len(row) != len(headers): continue
            try:
                raw_code = row[col_idx.get('code', 0)]
                code = re.sub(r'\D', '', raw_code)

                item = {
                    'code': code,
                    'name': row[col_idx.get('name', 1)],
                    'open_pct': clean_unit(row[col_idx.get('open_pct')]),
                    'today_auction_amt': clean_unit(row[col_idx.get('auc_amt')]),
                    'circ_mv': clean_unit(row[col_idx.get('circ_mv')]),
                    'curr_p': clean_unit(row[col_idx.get('curr_p')]),
                    'pct': clean_unit(row[col_idx.get('pct')]),
                    'history': {'yest_amt': 0}
                }
                if yest_amt_idx != -1:
                    item['yest_amt'] = clean_unit(row[yest_amt_idx])
                    item['history']['yest_amt'] = item['yest_amt']

                # 手动补充 1进2 标记 (默认全当做 1进2 复盘)
                item['tag_display'] = "1进2"

                data_map[code] = item
                count += 1
            except:
                continue

        print(f"{Fore.GREEN}✅ 加载了 {count} 条本地数据{Style.RESET_ALL}")
        return data_map
    except Exception as e:
        print(f"{Fore.RED}❌ 解析失败: {e}{Style.RESET_ALL}")
        return {}


# ================= 🛠️ 复盘主循环 =================

def run_fupan():
    pool_map = load_local_ths_data()
    if not pool_map: return

    # 策略池 (这里直接分析所有本地数据，或者只分析 strategy_pool.csv 里的)
    # 为了复盘全面，我们直接分析本地数据里的所有票
    display_list = []

    for code, item in pool_map.items():
        decision_str, score = get_strict_decision(item)
        item['decision'] = decision_str
        item['score'] = score
        display_list.append(item)

    display_list.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print(
        f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘后复盘报告 v6.0 {Style.RESET_ALL} | {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("=" * 140)
    print(
        f"{'代码':<7} {'名称':<8} {'现价':<7} {'竞价%':<7} {'现涨%':<7} {'竞价额(亿)':<11} {'竞/流%':<8} {'竞/昨%':<8} {'AI决策'}")
    print("-" * 140)

    for p in display_list:
        if p['score'] == 0: continue  # 过滤掉垃圾

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
    run_fupan()