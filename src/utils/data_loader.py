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

def load_history_basics():
    """加载昨收价，用于计算涨跌停价"""
    path = get_latest_history_path()
    info = {}
    if not os.path.exists(path): return info
    
    try:
        # 尝试读取
        try:
            with open(path, 'r', encoding='gbk') as f: content = f.read()
        except:
            with open(path, 'r', encoding='utf-8') as f: content = f.read()
            
        lines = content.split('\n')
        # 简单解析: 代码, 名称, 现价(昨收)
        # 假设 Table.txt 是同花顺导出，列比较多，这里简化查找
        for line in lines:
            if not line.strip(): continue
            parts = line.split()
            if len(parts) < 3: continue
            # 只有数字开头的行才可能是股票
            if parts[0].isdigit() and len(parts[0]) == 6:
                code = parts[0]
                # 寻找价格列，通常在第 2 或 3 列之后
                # 这是一个hacky方法，实际上 akshare 实时数据会带昨收，这里主要为了拿名字备用
                info[code] = {'name': parts[1]}
    except:
        pass
    return info
