# ==============================================================================
# 🛠️ DDD 策略离线回测脚本 (src/backtest/ddd_backtest.py)
# Version: 1.7 | 完美闭环版: 自动优先读取 _fixed 修复数据 + 强力搜救
# ==============================================================================
import os
import sys
import pandas as pd
import re
from colorama import init, Fore, Style

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

try:
    from src.strategies.ddd_mode import calculate_ddd_realtime
except ImportError:
    print(f"{Fore.RED}❌ 无法导入 src/strategies/ddd_mode.py")
    sys.exit(1)

init(autoreset=True)
DATA_DIR = os.path.join(project_root, 'data', 'input', 'ths')

# 🔥 调试目标
TARGET_DEBUG_CODES = ['601616', '601133'] 

def parse_val(v):
    if pd.isna(v): return 0.0
    s = str(v).strip().replace('%', '').replace(',', '')
    if s in ['--', 'nan', '', 'None']: return 0.0
    unit = 1.0
    if '亿' in s: unit = 100000000.0; s = s.replace('亿', '')
    elif '万' in s: unit = 10000.0; s = s.replace('万', '')
    try: return float(s) * unit
    except: return 0.0

def parse_boards(v):
    s = str(v).strip()
    if '首板' in s: return 1
    nums = re.findall(r'\d+', s)
    if not nums: return 0
    val = int(nums[-1])
    return 0 if val > 100 else val

def parse_ths_file(filepath):
    print(f"📖 读取: {os.path.basename(filepath)}")
    try:
        df = None
        for enc in ['gbk', 'utf-16', 'utf-8', 'gb18030']:
            try:
                df = pd.read_csv(filepath, sep=r'\t+', engine='python', encoding=enc, dtype=str)
                if len(df.columns) <= 1: df = pd.read_csv(filepath, sep=',', engine='python', encoding=enc, dtype=str)
                if any(k in str(list(df.columns)) for k in ['代码', 'Code']): break
            except: continue
        
        if df is None: return {}
        df.columns = [c.strip() for c in df.columns]
        
        col_map = {
            'code': ['代码'], 'name': ['名称'], 'open_pct': ['竞价涨幅'],
            'close_pct': ['涨跌幅', '涨幅'], 'bid_amt': ['早盘竞价金额', '竞价金额'],
            'amount': ['当日成交额', '成交额'], 'circ_mv': ['自由流通市值', '流通市值'],
            'boards': ['连板', '几天几板', '连板数'], 'high': ['最高'], 'low': ['最低'],
            'last_amt_backup': ['昨日成交额'] 
        }
        final_cols = {}
        for k, v in col_map.items():
            for c in v:
                found = next((col for col in df.columns if c in col), None)
                if found:
                    if k=='amount' and '昨日' in found: continue
                    final_cols[k] = found; break
        
        res = {}
        for _, row in df.iterrows():
            if 'code' not in final_cols: continue
            code = re.sub(r'\D', '', str(row[final_cols['code']])).zfill(6)
            res[code] = {
                'code': code,
                'name': str(row.get(final_cols.get('name'), '')).strip(),
                'open_pct': parse_val(row.get(final_cols.get('open_pct'))),
                'close_pct': parse_val(row.get(final_cols.get('close_pct'))),
                'bid_amt': parse_val(row.get(final_cols.get('bid_amt'))),
                'amount': parse_val(row.get(final_cols.get('amount'))),
                'circ_mv': parse_val(row.get(final_cols.get('circ_mv'))),
                'boards': parse_boards(row.get(final_cols.get('boards'))),
                'high': parse_val(row.get(final_cols.get('high'), 0)),
                'last_amt_backup': parse_val(row.get(final_cols.get('last_amt_backup'), 0))
            }
        return res
    except: return {}

def get_files():
    """
    智能获取文件逻辑：
    1. 扫描目录下所有 Table-*.txt
    2. 按日期归组
    3. 如果同一日期有 _fixed 版本，优先使用 _fixed
    4. 返回最新的两个日期文件
    """
    files = [f for f in os.listdir(DATA_DIR) if f.startswith('Table') and f.endswith('.txt')]
    file_map = {}
    
    for f in files:
        m = re.search(r'(\d{8})', f)
        if not m: continue
        date_int = int(m.group(1))
        
        is_fixed = '_fixed' in f
        
        # 如果该日期尚未记录，或者当前文件是 fixed 版本而记录的不是，则更新
        if date_int not in file_map:
            file_map[date_int] = f
        else:
            if is_fixed and '_fixed' not in file_map[date_int]:
                file_map[date_int] = f
    
    # 转换为列表并排序
    final_list = [{'path': os.path.join(DATA_DIR, v), 'date': k} for k, v in file_map.items()]
    final_list.sort(key=lambda x: x['date'], reverse=True)
    
    return (final_list[0], final_list[1]) if len(final_list) >= 2 else (None, None)

def run_backtest():
    f_t, f_p = get_files()
    if not f_t: return
    print(f"{Fore.CYAN}🚀 回测日期: {f_t['date']} (T-1: {f_p['date']}){Style.RESET_ALL}")
    
    # 打印文件名确认是否读取了 fixed
    print(f"   T  日文件: {os.path.basename(f_t['path'])}")
    print(f"   T-1日文件: {os.path.basename(f_p['path'])}")
    
    data_t = parse_ths_file(f_t['path'])
    data_p = parse_ths_file(f_p['path'])
    
    selected = []
    near_misses = [] 
    
    for code, item_t in data_t.items():
        is_debug = code in TARGET_DEBUG_CODES
        
        if code not in data_p: continue
        item_p = data_p[code]
        
        # 1. 连板数据补全
        boards_p = item_p['boards']
        if boards_p == 0 and item_p['close_pct'] >= 9.8: boards_p = 1
        
        # --- 数据完整性校验 ---
        yest_amt = item_p['amount']
        
        if yest_amt == 0:
            # 搜救逻辑 (如果昨文件也是坏的，尝试用今文件的备份列)
            if item_t['last_amt_backup'] > 0:
                yest_amt = item_t['last_amt_backup']
                if is_debug: print(f"   ⚠️ [Repair] 使用 T 日表中的昨日数据: {int(yest_amt/10000)}w")
            elif item_t['amount'] > 0:
                yest_amt = item_t['amount'] # 拙劣估算
                if is_debug: print(f"   ⚠️ [Repair] 使用今日成交额估算: {int(yest_amt/10000)}w")
        
        if yest_amt == 0: 
            if is_debug: print(f"   ❌ [Fail] 彻底无法获取昨日成交额，跳过")
            continue
        # -----------------------------

        # 2. 策略计算
        row_sim = {'open_pct': item_t['open_pct'], 'auc_amt': item_t['bid_amt']/10000.0}
        hist_sim = {'circ_mv': item_p['circ_mv'], 'yest_amt': yest_amt, 'last_bid_amt': item_p['bid_amt'], 'boards': boards_p}
        
        score, dec, reason = calculate_ddd_realtime(row_sim, hist_sim)
        
        if is_debug:
            print(f"   ✅ [Calc Done] 得分={score} | 原因={reason}")

        bid_yest_ratio = (item_t['bid_amt'] / yest_amt) if yest_amt > 0 else 0
        
        profit = item_t['close_pct'] - item_t['open_pct']
        is_zt = item_t['close_pct'] >= 9.8
        
        res_obj = {
            'code': code, 'name': item_t['name'], 'open': item_t['open_pct'],
            'close': item_t['close_pct'], 'profit': profit, 'is_zt': is_zt,
            'dec': dec, 'reason': reason, 'boards_p': boards_p,
            'bid_amt': item_t['bid_amt']
        }

        if score >= 90:
            selected.append(res_obj)
        elif score >= 80:
            res_obj['dec'] = "👀观察"
            selected.append(res_obj)
        else:
            # 搜救
            cond_board = (boards_p >= 1 and item_t['open_pct'] > 2.0 and "一字" not in reason)
            cond_ratio = (bid_yest_ratio > 0.07 and item_t['open_pct'] > 2.0 and "一字" not in reason)
            cond_missing = (boards_p == 0 and item_t['open_pct'] > 3.5 and item_p['close_pct'] > 5.0)
            
            if cond_board or cond_ratio or cond_missing:
                if cond_ratio: res_obj['reason'] += f"(🔥竞昨比{bid_yest_ratio*100:.1f}%)"
                elif cond_missing: res_obj['reason'] += "(疑似连板遗漏)"
                near_misses.append(res_obj)

    print_table("🏆 DDD 策略选中标的", selected)
    near_misses.sort(key=lambda x: x['open'], reverse=True)
    print_table("👀 观察池 (人工二次筛选)", near_misses[:25], is_miss=True)

def print_table(title, data, is_miss=False):
    if not data: return
    print(f"\n{Fore.WHITE}== {title} =={Style.RESET_ALL}")
    print(f"{'代码':<7} {'名称':<8} {'T-1板':<6} {'竞价%':<6} {'收盘%':<6} {'浮盈%':<6} {'状态':<6} {'说明/淘汰原因'}")
    print("-" * 110)
    if not is_miss: data.sort(key=lambda x: (x['boards_p'], x['open']), reverse=True)
    for r in data:
        p_color = Fore.RED if r['profit'] > 0 else Fore.GREEN
        status = "涨停🔥" if r['is_zt'] else ("收红" if r['profit']>0 else "吃面")
        reason_str = f"{Fore.CYAN}{r['reason']}{Style.RESET_ALL}" if is_miss else r['reason']
        print(f"{r['code']:<7} {r['name']:<8} {r['boards_p']:<6} {r['open']:>6.2f} {r['close']:>6.2f} {p_color}{r['profit']:>6.2f}{Style.RESET_ALL} {status:<6} {reason_str}")

if __name__ == '__main__':
    run_backtest()