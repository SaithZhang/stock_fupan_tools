# ==============================================================================
# 🛠️ DDD 策略离线回测脚本 (src/backtest/ddd_backtest.py)
# 作用: 使用本地同花顺数据 (T日竞价 + T-1日历史) 回测 DDD 策略的胜率
# ==============================================================================
import os
import sys
import pandas as pd
import re
from colorama import init, Fore, Style

# 添加项目根目录到路径，以便导入 strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from src.strategies.ddd_mode import calculate_ddd_realtime

init(autoreset=True)

# --- 配置 ---
DATA_DIR = os.path.join(project_root, 'data', 'input', 'ths')

# 自动寻找最新的两个文件
def get_test_files():
    files = [f for f in os.listdir(DATA_DIR) if f.startswith('Table') and f.endswith('.txt')]
    # 提取日期
    file_map = []
    for f in files:
        m = re.search(r'[-_]?(\d{8})', f)
        if m:
            file_map.append({'path': os.path.join(DATA_DIR, f), 'date': int(m.group(1))})
    
    # 按日期排序 (从大到小)
    file_map.sort(key=lambda x: x['date'], reverse=True)
    
    if len(file_map) < 2:
        print(f"{Fore.RED}❌ 数据文件不足，至少需要2天的数据 (T 和 T-1)")
        return None, None
        
    return file_map[0], file_map[1]

# --- 数据解析 helper (简化版) ---
def parse_ths_file(filepath):
    print(f"   📖 解析文件: {os.path.basename(filepath)} ...")
    try:
        # 尝试多种编码
        df = None
        for enc in ['gbk', 'utf-8', 'utf-16']:
            try:
                df = pd.read_csv(filepath, sep=r'\t+', engine='python', encoding=enc, dtype=str)
                if '代码' in df.columns or ' 名称' in df.columns:
                    break
            except:
                continue
                
        if df is None: return {}
        
        df.columns = [c.strip() for c in df.columns]
        
        # 映射列
        item_map = {}
        
        # 查找关键列
        col_code = next((c for c in df.columns if '代码' in c), None)
        col_name = next((c for c in df.columns if '名称' in c), None)
        col_zt = next((c for c in df.columns if '连板' in c or '几天几板' in c or '连续涨停' in c), None) # 连板天数
        col_mv = next((c for c in df.columns if '流通市值' in c), None)
        
        # 优先匹配 '当日成交额' (对于历史文件，我们需要当天的成交额作为 yest_amt)
        # 其次匹配 '成交额'
        col_amt = next((c for c in df.columns if '当日成交额' in c), None)
        if not col_amt: col_amt = next((c for c in df.columns if '成交额' in c and '昨日' not in c), None)
        if not col_amt: col_amt = next((c for c in df.columns if '成交额' in c), None)
        
        col_bid = next((c for c in df.columns if '早盘竞价金额' in c), None)
        col_op = next((c for c in df.columns if '竞价涨幅' in c), None)
        col_cp = next((c for c in df.columns if '涨幅' in c and '竞价' not in c), None) # 收盘涨幅
        
        # Capture Yesterday's Amount from the same file (Backup)
        col_last_amt = next((c for c in df.columns if '昨日成交额' in c), None)
        
        for _, row in df.iterrows():
            code_raw = str(row[col_code])
            code = re.sub(r'\D', '', code_raw).zfill(6)
            
            # --- 解析数值 ---
            def parse_val(v):
                if pd.isna(v): return 0.0
                s = str(v).strip().replace('%', '')
                if s in ['--', 'nan']: return 0.0
                unit = 1.0
                if '亿' in s: unit = 100000000.0; s = s.replace('亿', '')
                elif '万' in s: unit = 10000.0; s = s.replace('万', '')
                try: return float(s) * unit
                except: return 0.0

            # 连板数解析
            boards = 0
            if col_zt:
                b_str = str(row.get(col_zt, ''))
                nums = re.findall(r'\d+', b_str)
                if nums: boards = int(nums[-1])
                
                # Sanity Check (THS magic number 65537 fix)
                if boards > 100: boards = 0
            
            item = {
                'code': code,
                'name': str(row.get(col_name, '')).strip(),
                'boards': boards,
                'circ_mv': parse_val(row.get(col_mv)),
                'amount': parse_val(row.get(col_amt)),
                'last_amount': parse_val(row.get(col_last_amt)), # Backup source
                'bid_amt': parse_val(row.get(col_bid)),
                'open_pct': parse_val(row.get(col_op)),
                'close_pct': parse_val(row.get(col_cp))
            }
            item_map[code] = item
            
        return item_map
        
    except Exception as e:
        print(f"{Fore.RED}❌ 解析出错: {e}")
        return {}

# --- 主逻辑 ---
def run_backtest():
    print(f"{Fore.CYAN}🚀 DDD 策略回测启动...{Style.RESET_ALL}")
    
    # 1. 确定文件
    file_today, file_yest = get_test_files()
    if not file_today: return
    
    print(f"📅 T 日 (模拟今日): {os.path.basename(file_today['path'])}")
    print(f"🔙 T-1日 (历史背景): {os.path.basename(file_yest['path'])}")
    
    # 2. 加载数据
    data_today = parse_ths_file(file_today['path'])
    data_yest = parse_ths_file(file_yest['path'])
    
    if not data_today or not data_yest:
        print("❌ 数据加载失败")
        return

    print(f"✅ 数据就绪: T日 {len(data_today)} 条 | T-1日 {len(data_yest)} 条")
    
    # 3. 模拟竞价筛选
    results = []
    
    print(f"\n{Fore.YELLOW}⏳ 正在执行 9:25 模拟筛选...{Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}⏳ 正在执行 9:25 模拟筛选...{Style.RESET_ALL}")
    
    for code, item_t in data_today.items():
        # 必须在昨天有数据才能判断 (因为需要昨成交、昨连板状态)
        if code not in data_yest: continue
        
        item_y = data_yest[code]

        
        # --- Fallback Logic for Dirty Data ---
        # 1. Fix Boards: If boards=0 but T-1 was Limit Up, assume 1 board.
        boards_prev = item_y['boards']
        if boards_prev == 0 and item_y['close_pct'] >= 9.8:
            boards_prev = 1
            
        # 2. Fix Amount: If T-1 Amount is missing, use T-Day's 'Yesterday Amount'
        yest_amt = item_y['amount']
        if yest_amt == 0 and item_t['last_amount'] > 0:
            yest_amt = item_t['last_amount']

        
        # 构造 Strategy 需要的包
        # Realtime row (simulated from T day data)
        # 注意: calculate_ddd_realtime 期望 'auc_amt' 单位为 万
        row_sim = {
            'open_pct': item_t['open_pct'],
            'auc_amt': item_t['bid_amt'] / 10000.0  # 转为万
        }
        
        # History item (from T-1 day data)
        # 修正: 'last_bid_amt' 是 昨天的竞价金额，即 T-1 日的 bid_amt
        hist_sim = {
            'circ_mv': item_y['circ_mv'],
            'yest_amt': yest_amt,
            'boards': boards_prev,
            'last_bid_amt': item_y['bid_amt'] 
        }
        
        # 执行策略
        score, dec, detail = calculate_ddd_realtime(row_sim, hist_sim)
        
        # DEBUG: Print details for Guangdian 601616
        if code == '601616':
             print(f"🔎 DEBUG 601616: Score={score} | Dec='{dec}' | Reason='{detail}'")
             print(f"   Inputs: MV={hist_sim['circ_mv']/100000000:.2f}Y | YestAmt={hist_sim['yest_amt']/100000000:.2f}Y | Boards={hist_sim['boards']}")

        if score > 0:
            # 记录结果
            is_win = item_t['close_pct'] >= 9.8 
            profit = item_t['close_pct'] - item_t['open_pct']
            
            res = {
                'code': code,
                'name': item_t['name'],
                'decision': dec,
                'detail': detail,
                'open': item_t['open_pct'],
                'close': item_t['close_pct'],
                'profit': profit,
                'is_win': is_win,
                'boards_prev': item_y['boards']
            }
            results.append(res)

    # 4. 输出报告
    results.sort(key=lambda x: x['boards_prev'])
    
    print(f"\n{Fore.WHITE}📊 回测结果报告 (Target Date: {file_today['date']}){Style.RESET_ALL}")
    print("=" * 100)
    print(f"{'代码':<8} {'名称':<8} {'T-1板':<6} {'策略标签':<12} {'开盘%':<6} {'收盘%':<6} {'浮盈%':<6} {'结果'}")
    print("-" * 100)
    
    total_count = len(results)
    win_count = 0
    pos_count = 0
    total_profit = 0
    
    for r in results:
        res_str = f"{Fore.RED}涨停🔥" if r['is_win'] else (f"{Fore.RED}收红" if r['profit'] > 0 else f"{Fore.GREEN}收绿")
        if r['is_win']: win_count += 1
        if r['profit'] > 0: pos_count += 1
        total_profit += r['profit']
        
        color_p = Fore.RED if r['profit'] > 0 else Fore.GREEN
        
        print(f"{r['code']:<8} {r['name']:<8} {r['boards_prev']:<6} {r['decision']:<12} {r['open']:>6.2f} {r['close']:>6.2f} {color_p}{r['profit']:>6.2f}{Style.RESET_ALL} {res_str}{Style.RESET_ALL}")

    print("=" * 100)
    if total_count > 0:
        avg_profit = total_profit / total_count
        win_rate = (win_count / total_count) * 100
        pos_rate = (pos_count / total_count) * 100
        
        print(f"🎯 选中标的: {total_count} 只")
        print(f"🔥 涨停命中: {win_count} 只 (胜率 {win_rate:.1f}%)")
        print(f"📈 收盘红盘: {pos_count} 只 (胜率 {pos_rate:.1f}%)")
        print(f"💰 平均肉度: {Fore.RED if avg_profit>0 else Fore.GREEN}{avg_profit:.2f}%{Style.RESET_ALL}")
    else:
        print("⚠️ 该日无符合 DDD 策略的标的。")

if __name__ == '__main__':
    run_backtest()
