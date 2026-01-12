import os
import re
import pandas as pd
import sys

def get_project_root():
    """Get the project root directory."""
    # This assumes the file is in src/utils/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = get_project_root()
STRATEGY_POOL_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')

def get_latest_history_path():
    """获取最新的昨收数据"""
    base_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')
    if not os.path.exists(base_dir): return "Table.txt"
    files = [f for f in os.listdir(base_dir) if f.startswith("Table") and f.endswith(".txt")]
    files.sort(key=lambda x: x, reverse=True) # 简单按文件名排序(日期)
    return os.path.join(base_dir, files[0]) if files else "Table.txt"

def load_holdings():
    """加载持仓列表 (手动解析版，最稳健)"""
    if not os.path.exists(HOLDINGS_PATH): return {}
    holdings = {}
    try:
        with open(HOLDINGS_PATH, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        if not lines: return {}
        
        # 1. 找表头
        header_idx = -1
        header_parts = []
        for i, line in enumerate(lines):
            if '代码' in line and ('成本' in line or '价' in line):
                header_idx = i
                # 用正则按空白切分
                header_parts = re.split(r'\s+', line)
                break
        
        if header_idx == -1: return {}
        
        # 2. 找列索引
        idx_code = -1
        idx_cost = -1
        idx_vol = -1
        
        for i, h in enumerate(header_parts):
            if '代码' in h: idx_code = i
            elif '成本' in h: idx_cost = i
            elif '余额' in h or ('数量' in h and '冻结' not in h): idx_vol = i
            
        if idx_code == -1: return {}
        
        # 3. 解析数据
        for line in lines[header_idx+1:]:
            parts = re.split(r'\s+', line)
            if len(parts) <= idx_code: continue
            
            try:
                # 代码
                raw_code = parts[idx_code]
                code = re.sub(r'\D', '', raw_code).zfill(6)
                
                # 成本
                cost = 0.0
                if idx_cost != -1 and len(parts) > idx_cost:
                    try: cost = float(parts[idx_cost])
                    except: pass
                
                # 数量
                vol = 0
                if idx_vol != -1 and len(parts) > idx_vol:
                    try: vol = int(parts[idx_vol])
                    except: pass
                
                holdings[code] = {'cost': cost, 'vol': vol}
            except:
                continue
                
    except Exception as e:
        print(f"持仓加载异常: {e}")
        pass
        
    return holdings



def load_manual_focus():
    """加载手动关注名单"""
    if not os.path.exists(MANUAL_FOCUS_PATH): return {}
    pool = {}
    current_tag = "手动"
    
    try:
        with open(MANUAL_FOCUS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Check for section headers
            if line.startswith('#'):
                # Try to extract meaningful tag from comment
                clean_comment = line.lstrip('#').strip()
                if clean_comment.startswith('---'):
                    clean_comment = clean_comment.strip('- ')
                
                if clean_comment:
                    current_tag = clean_comment
                continue
            
            # Parse code
            parts = line.split()
            if parts:
                code = parts[0]
                if code.isdigit() and len(code) == 6:
                     # Remove potential inline comments if any, though parts[0] is just code
                     pool[code] = current_tag
                     
    except Exception as e:
        print(f"手动关注加载失败: {e}")
        
    return pool

def load_pool():
    """加载策略池，返回 {code: tag} (包含 CSV 策略池 + manual_focus.txt)"""
    pool = {}
    
    # 1. Load CSV
    if os.path.exists(STRATEGY_POOL_PATH):
        try:
            df = pd.read_csv(STRATEGY_POOL_PATH)
            for _, row in df.iterrows():
                code = str(row.get('sina_code', ''))[2:]
                if not code: code = str(row.get('code', '')).zfill(6)
                pool[code] = str(row.get('tag', ''))
        except:
            pass
            
    # 2. Load Manual Focus
    try:
        manual = load_manual_focus()
        pool.update(manual)
    except:
        pass
        
    return pool

def load_pool_full():
    """
    加策略池完整数据，返回 {code: dict_row}
    包含: tag, limit_up_type, deviation_val, call_auction_ratio 等
    """
    pool = {}
    
    # 1. Load CSV
    if os.path.exists(STRATEGY_POOL_PATH):
        try:
            # KeepDefaultNA=False to avoid 'NaN' string issues, but pandas might still do it.
            # Convert to str where necessary
            df = pd.read_csv(STRATEGY_POOL_PATH, dtype=str).fillna('')
            for _, row in df.iterrows():
                code = str(row.get('sina_code', ''))[2:]
                if not code: code = str(row.get('code', '')).zfill(6)
                
                # Convert numeric fields back to float for calculation if needed, 
                # or keep as simple props.
                # Here we store the raw row dict (with strings) or converted.
                # Let's clean it up slightly
                item = row.to_dict()
                item['code'] = code # ensure pure code
                
                # Tag aggregation from CSV
                pool[code] = item
        except Exception as e:
            print(f"策略池加载失败: {e}")
            pass
            
    # 2. Logic for Manual Focus integration into 'Full' pool?
    # Manual focus currently only has 'Tag'. 
    # If a stock is ONLY in manual focus but not in CSV, we create a dummy entry.
    # If it is in Both, we might want to ensure the 'tag' reflects manual focus too?
    # But usually pool_generator already merges manual focus into the CSV 'tag' column.
    # So we just check for manual-only items.
    
    try:
        manual_map = load_manual_focus()
        for code, tag in manual_map.items():
            if code not in pool:
                pool[code] = {
                    'code': code, 
                    'name': '手动关注', 
                    'tag': tag,
                    'sina_code': f"sz{code}" if code.startswith('0') or code.startswith('3') else f"sh{code}" # simple guess
                }
    except:
        pass
        
    return pool

def load_history_basics():
    """
    加载历史数据基础信息 (昨收, 行业, 市值等)
    返回: {code: {'name': str, 'industry': str, 'close': float, 'mcap': float}}
    """
    path = get_latest_history_path()
    info = {}
    if not os.path.exists(path): return info
    
    try:
        # Load File with robust strategy
        df = None
        # 1. Regex + UTF-8 (Prioritize for copied text)
        try:
             df = pd.read_csv(path, sep=r'\s+', encoding='utf-8', on_bad_lines='skip')
             cols = [str(c) for c in df.columns]
             if not any("代码" in c for c in cols): df = None
        except: pass

        # 2. Regex + GBK
        if df is None:
            try:
                df = pd.read_csv(path, sep=r'\s+', encoding='gbk', on_bad_lines='skip')
            except: pass

        # 3. Fallback
        if df is None:
             try: df = pd.read_csv(path, sep='\t', encoding='gbk')
             except: return info
        
        # Parse Cols
        col_code, col_name, col_ind, col_close, col_mcap = None, None, None, None, None
        
        for col in df.columns:
            c = str(col).strip()
            if "代码" in c: col_code = col
            if "名称" in c: col_name = col
            if "行业" in c: col_ind = col
            if "现价" in c or "收盘" in c: col_close = col
            if "流通市值" in c: col_mcap = col
            
        if not col_code: return info
        
        # Clean Code
        df[col_code] = df[col_code].astype(str).str.zfill(6)
        
        for _, row in df.iterrows():
            try:
                code = row[col_code]
                if not code.isdigit():
                    code = re.sub(r"\D", "", code).zfill(6)
                
                name = str(row[col_name]).strip() if col_name else '未知'
                industry = str(row[col_ind]).strip() if col_ind else '未知'
                
                close = 0.0
                if col_close:
                    try: close = float(row[col_close])
                    except: pass
                    
                mcap = 0.0
                if col_mcap:
                    try: 
                        val_str = str(row[col_mcap]).replace('亿', '*100000000').replace('万', '*10000')
                        mcap = eval(val_str)
                    except: pass

                info[code] = {
                    'name': name,
                    'industry': industry,
                    'close': close,
                    'mcap': mcap
                }
            except: continue
            
    except Exception as e:
        print(f"基础数据加载失败: {e}")
        pass
        
    return info

def get_latest_call_auction_file():
    """
    Get the latest call auction file from data/input/call_auction/
    Returns: file_path (str) or None
    """
    base_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'call_auction')
    if not os.path.exists(base_dir): return None
    
    files = [f for f in os.listdir(base_dir) if f.lower().endswith(('.txt', '.csv', '.xls', '.xlsx'))]
    if not files: return None
    
    # Sort by mtime
    files.sort(key=lambda x: os.path.getmtime(os.path.join(base_dir, x)), reverse=True)
    return os.path.join(base_dir, files[0])

def parse_call_auction_file(file_path):
    """
    Parse a call auction export file (txt/csv/excel) using Pandas for robustness.
    Returns: DataFrame with columns ['code', 'name', 'auc_amt', 'open_pct'] or None
    """
    if not os.path.exists(file_path): return None

    df = None
    # Prioritize Separators: Tab (THS default), then whitespace
    separators = [r'\t+', r'\s+'] 
    encodings = ['gbk', 'utf-16', 'utf-8']
    
    for enc in encodings:
        for sep in separators:
            try:
                # Read with flexible separator and engine
                temp_df = pd.read_csv(file_path, sep=sep, engine='python', encoding=enc, dtype=str)
                # Cleanup column names
                temp_df.columns = [str(c).strip() for c in temp_df.columns]
                
                if any("代码" in c for c in temp_df.columns) and len(temp_df) > 0:
                    df = temp_df
                    break
            except:
                continue
        if df is not None: break
        
    if df is None:
        print(f"❌ 无法解析文件: {file_path}")
        return None

    # Map Columns
    cols = df.columns
    col_code = next((c for c in cols if "代码" in c), None)
    col_name = next((c for c in cols if "名称" in c), None)
    
    # Priority: Call Auction > Open > Amount
    col_amt = next((c for c in cols if "早盘竞价金额" in c), None)
    if not col_amt: col_amt = next((c for c in cols if "竞价金额" in c or "竞价额" in c), None)
    if not col_amt: col_amt = next((c for c in cols if "金额" in c or "竞价" in c), None)
    
    # Yesterday Amount (Optional)
    col_last_amt = next((c for c in cols if "昨日成交额" in c or "昨成交" in c), None)
    
    # Priority: Call Pct > Open Pct > Pct
    col_pct = next((c for c in cols if "竞价涨幅" in c), None)
    if not col_pct: col_pct = next((c for c in cols if "开盘涨幅" in c), None)
    if not col_pct: col_pct = next((c for c in cols if "涨幅" in c), None)

    if not col_code or not col_amt:
        print(f"❌ 关键列缺失: Code={col_code}, Amt={col_amt}, Pct={col_pct}")
        return None

    res_map = {}
    
    for _, row in df.iterrows():
        try:
            # Code
            raw_code = str(row[col_code])
            code = re.sub(r"\D", "", raw_code).zfill(6)
            
            # Name
            name = str(row[col_name]).strip() if col_name else "未知"
            
            # Amt
            raw_amt = str(row[col_amt])
            auc_val = 0.0
            
            # Handle "1.23亿", "500万", or raw large numbers
            if '亿' in raw_amt:
                auc_val = float(raw_amt.replace('亿', '')) * 10000
            elif '万' in raw_amt:
                auc_val = float(raw_amt.replace('万', ''))
            elif raw_amt.replace('.','').replace('-','').isdigit():
                val = float(raw_amt)
                # Heuristic: If value > 1 Million, assume it's raw Unit (Yuan), convert to Wan
                # If value < 100000, maybe it's already Wan? 
                # THS usually exports Raw Yuan for "早盘竞价金额" (e.g. 4084080)
                if val > 10000: 
                    auc_val = val / 10000.0
                else: 
                    # Ambiguous case: 5000 could be 5000 Yuan or 5000 Wan. 
                    # Assume Yuan for consistency with THS raw exports.
                    auc_val = val / 10000.0
            
            # Pct
            pct_val = 0.0
            if col_pct:
                try:
                    pct_str = str(row[col_pct]).replace('%', '').replace('+', '')
                    pct_val = float(pct_str)
                except: pct_val = 0.0
                
            # Yesterday Amount
            last_amt = 0.0
            if col_last_amt:
                try:
                    r_last = str(row[col_last_amt])
                    if '亿' in r_last:
                        last_amt = float(r_last.replace('亿', '')) * 10000
                    elif '万' in r_last:
                        last_amt = float(r_last.replace('万', ''))
                    elif r_last.replace('.','').isdigit():
                        val = float(r_last)
                        if val > 10000: last_amt = val / 10000.0
                        else: last_amt = val / 10000.0 # assume yuan
                except: pass

            res_map[code] = {
                'code': code,
                'name': name,
                'auc_amt': auc_val, # Unit: Wan
                'open_pct': pct_val,
                'last_amt': last_amt # Unit: Wan
            }
        except: continue
        
    if res_map:
        return pd.DataFrame(list(res_map.values()))
    return None
