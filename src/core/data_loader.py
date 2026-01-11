import pandas as pd
import akshare as ak
import os
import re
import glob
from colorama import init, Fore

init(autoreset=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
TDX_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'tdx')
THS_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')


def clean_code(code_str):
    return re.sub(r'\D', '', str(code_str))


def find_latest_file(directory, extensions=[".txt", ".csv", ".xlsx", ".xls"]):
    if not os.path.exists(directory): return None
    candidates = []
    for ext in extensions:
        candidates.extend(glob.glob(os.path.join(directory, f"*{ext}")))
    if not candidates: return None
    return max(candidates, key=os.path.getmtime)


def safe_float(val):
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if s == '--' or s == '' or s.lower() == 'nan': return 0.0
    if '%' in s: s = s.replace('%', '')
    s = s.replace(',', '')
    # 处理中文单位
    unit = 1.0
    if '亿' in s:
        s = s.replace('亿', '')
        unit = 100000000.0
    elif '万' in s:
        s = s.replace('万', '')
        unit = 10000.0
    try:
        f = float(s) * unit
        return f
    except:
        return 0.0


def safe_str(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    if s.lower() == 'nan' or s == '--': return ""
    return s


# ================= 1. 加载同花顺 (修复版) =================
def load_ths_data():
    # 改进的文件查找逻辑：优先找文件名带日期的最新文件
    # 支持格式: Table-20260117.txt, Table_20260117.txt
    if not os.path.exists(THS_DIR): return {}
    
    files = os.listdir(THS_DIR)
    candidates = []
    
    for f in files:
        if f.startswith("Table") and f.endswith(".txt"):
            full_path = os.path.join(THS_DIR, f)
            # 尝试提取日期 (支持 - 或 _)
            date_match = re.search(r'[-_]?(20\d{6})', f)
            date_int = int(date_match.group(1)) if date_match else 0
            
            # Table.txt 视为无日期(0) 或 极大(99999999) 根据策略
            # 这里策略：如果有带日期的，取日期最大的；如果没有，取最近修改的 Table.txt
            if f == "Table.txt":
                 candidates.append({'path': full_path, 'date': 0, 'mtime': os.path.getmtime(full_path)})
            else:
                 candidates.append({'path': full_path, 'date': date_int, 'mtime': 0})
    
    target_file = None
    if candidates:
        # 1. 优先按文件名里的日期排序
        dated = [c for c in candidates if c['date'] > 0]
        if dated:
            dated.sort(key=lambda x: x['date'], reverse=True)
            target_file = dated[0]['path']
        else:
            # 2. 否则按文件修改时间
            candidates.sort(key=lambda x: x['mtime'], reverse=True)
            target_file = candidates[0]['path']
            
    if not target_file: return {}

    if not target_file: return {}

    print(f"{Fore.BLUE}📂 [优先] 加载同花顺数据: {os.path.basename(target_file)}")
    return _parse_ths_csv(target_file)


def load_yesterday_ths_data():
    """
    加载最近一个交易日(不含今日)的数据，用于计算昨日涨停溢价、昨日量比等
    """
    # 1. 先找到今天的日期 (从最新的文件名里提取)
    if not os.path.exists(THS_DIR): return {}
    files = os.listdir(THS_DIR)
    latest_date = 0
    for f in files:
        if f.startswith("Table") and f.endswith(".txt"):
             date_match = re.search(r'[-_]?(20\d{6})', f)
             if date_match:
                 d = int(date_match.group(1))
                 if d > latest_date: latest_date = d
    
    if latest_date == 0: return {}
    
    # 2. 找上一个文件
    prev_file_path = find_previous_ths_file(latest_date)
    if not prev_file_path:
        print(f"{Fore.YELLOW}⚠️ 未找到昨日THS数据文件")
        return {}
        
    print(f"{Fore.BLUE}🔙 加载昨日同花顺数据: {os.path.basename(prev_file_path)}")
    return _parse_ths_csv(prev_file_path)


def _parse_ths_csv(target_file):
    try:
        # --- 关键修改：使用正则分隔符处理不规则的 tab ---
        # sep=r'\t+' 表示把连续的 tab 当作一个分隔符
        try:
            df = pd.read_csv(target_file, sep=r'\t+', engine='python', encoding='gbk', dtype=str)
        except:
            try:
                df = pd.read_csv(target_file, sep=r'\t+', engine='python', encoding='utf-16', dtype=str)
            except:
                df = pd.read_csv(target_file, sep=r'\t+', engine='python', encoding='utf-8', dtype=str)

        df.columns = [c.strip() for c in df.columns]

        # 打印前几列名，用于调试
        # print(f"   (Debug) 解析列名: {df.columns.tolist()[:5]}...")

        data_map = {}

        col_code = next((c for c in df.columns if '代码' in c), None)
        col_name = next((c for c in df.columns if '名称' in c), None)
        col_price = next((c for c in df.columns if '现价' in c), None)
        col_pct = next((c for c in df.columns if '涨幅' in c and '竞价' not in c and '10' not in c and '3' not in c), None)
        col_amt = next((c for c in df.columns if '成交额' in c and '3日' not in c and '5日' not in c), None)
        col_to = next((c for c in df.columns if '换手' in c), None)

        col_zt_days = next((c for c in df.columns if '连续涨停' in c or '连板' in c), None)
        col_reason = next((c for c in df.columns if '原因' in c), None)
        col_desc = next((c for c in df.columns if '几天几板' in c), None)
        col_pct10 = next((c for c in df.columns if '10日涨幅' in c), None)
        col_auc_pct = next((c for c in df.columns if '竞价涨幅' in c), None)
        
        # --- New Columns ---
        col_auc_amt = next((c for c in df.columns if '早盘竞价金额' in c), None)
        col_open_num = next((c for c in df.columns if '开板次数' in c), None)
        col_industry = next((c for c in df.columns if '所属行业' in c), None)
        col_pct20 = next((c for c in df.columns if '20日涨幅' in c), None)

        if not col_code:
            print(f"{Fore.RED}❌ 解析失败：未找到【代码】列，可能是文件格式太乱。")
            return {}

        for _, row in df.iterrows():
            code = clean_code(row[col_code])
            if len(code) != 6: continue

            # 基础数据
            name = safe_str(row.get(col_name))
            price = safe_float(row.get(col_price))
            pct = safe_float(row.get(col_pct))

            # --- 校验：防止错位 (如把价格当成涨幅) ---
            if abs(pct) > 60 and 'N' not in name and 'C' not in name:
                pct = 0.0
            if '%' in name or len(name) > 10:
                continue

            item = {
                'source': 'THS',
                'code': code,
                'name': name,
                'price': price,
                'today_pct': pct,
                'amount': safe_float(row.get(col_amt)),
                'turnover': safe_float(row.get(col_to)),
                'pct_10': safe_float(row.get(col_pct10)),
                'open_pct': safe_float(row.get(col_auc_pct)),
                
                # New Fields
                'call_auction_amount': safe_float(row.get(col_auc_amt)),
                'open_num': int(safe_float(row.get(col_open_num))) if col_open_num else 0,
                'industry': safe_str(row.get(col_industry)),
                'pct_20': safe_float(row.get(col_pct20)),
            }

            item['limit_days'] = int(safe_float(row.get(col_zt_days, 0)))
            item['is_zt'] = (item['limit_days'] > 0 and item['today_pct'] > 0) or (item['today_pct'] > 9.8)

            tags = []
            desc = safe_str(row.get(col_desc))
            if desc and len(desc) < 20: tags.append(desc) 

            if item['limit_days'] > 0: tags.append(f"{item['limit_days']}板")

            reason = safe_str(row.get(col_reason))
            if reason: tags.append(reason)

            item['tag_ths'] = "/".join(tags)
            data_map[code] = item

        print(f"   ↳ 成功解析 {len(data_map)} 条数据")
        return data_map
    except Exception as e:
        print(f"{Fore.RED}❌ 读取失败: {e}")
        return {}


def find_previous_ths_file(current_date_int):
    """
    寻找比 current_date_int 小的最近一个日期的文件
    """
    if not os.path.exists(THS_DIR): return None
    
    files = os.listdir(THS_DIR)
    candidates = []
    
    for f in files:
        if f.startswith("Table") and f.endswith(".txt"):
            full_path = os.path.join(THS_DIR, f)
            date_match = re.search(r'[-_]?(20\d{6})', f)
            if date_match:
                d_int = int(date_match.group(1))
                if d_int < current_date_int:
                    candidates.append({'path': full_path, 'date': d_int})
    
    if not candidates: return None
    
    # Sort descending to get the closest past date
    candidates.sort(key=lambda x: x['date'], reverse=True)
    return candidates[0]['path']



# ================= 2. 加载通信达 (保持稳定) =================
def load_tdx_data():
    target_file = find_latest_file(TDX_DIR)
    if not target_file: return {}

    print(f"{Fore.CYAN}📂 [替补] 加载通信达数据: {os.path.basename(target_file)}")
    try:
        # 通信达通常列很整齐，不需要正则
        if target_file.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(target_file, dtype=str)
        else:
            try:
                df = pd.read_csv(target_file, sep=None, engine='python', encoding='gbk', dtype=str)
            except:
                df = pd.read_csv(target_file, sep=None, engine='python', encoding='utf-8', dtype=str)

        df.columns = [str(c).replace('Z', '').strip() for c in df.columns]
        data_map = {}

        col_code = next((c for c in df.columns if '代码' in c), None)
        col_name = next((c for c in df.columns if '名称' in c), None)
        col_pct = next((c for c in df.columns if '涨幅' in c), None)
        col_price = next((c for c in df.columns if '现价' in c), None)
        col_amt = next((c for c in df.columns if '金额' in c), None)
        col_to = next((c for c in df.columns if '换手' in c), None)

        if not col_code: return {}

        for _, row in df.iterrows():
            code = clean_code(row[col_code])
            if len(code) != 6: continue

            item = {
                'source': 'TDX',
                'code': code,
                'name': safe_str(row.get(col_name)),
                'price': safe_float(row.get(col_price)),
                'today_pct': safe_float(row.get(col_pct)),
                'amount': safe_float(row.get(col_amt)),
                'turnover': safe_float(row.get(col_to)),
                'pct_10': 0.0,
                'limit_days': 0,
                'is_zt': False
            }
            if item['today_pct'] > 9.8: item['is_zt'] = True
            data_map[code] = item
        return data_map
    except:
        return {}


# ================= 3. API 兜底 =================
def fetch_akshare_ladder():
    print(f"{Fore.MAGENTA}🌐 [兜底] 正在联网核对连板梯队 (AkShare)...")
    ladder_map = {}
    try:
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        df_zt = ak.stock_zt_pool_em(date=today)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                code = row['代码']
                days = int(row['连板数'])
                reason = safe_str(row.get('涨停原因类别'))
                tag = f"{days}板"
                if days == 1 and row['首次封板时间'] == row['最后封板时间']: tag = "首板/硬"
                ladder_map[code] = {'limit_days': days, 'tag_api': f"{tag}/{reason}", 'is_zt': True}

        df_zb = ak.stock_zt_pool_zbgc_em(date=today)
        if not df_zb.empty:
            for _, row in df_zb.iterrows():
                ladder_map[row['代码']] = {'limit_days': 0, 'tag_api': "炸板", 'is_zt': False}
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 联网失败: {e}")
    return ladder_map


# ================= 主入口 =================
def get_merged_data():
    map_ths = load_ths_data()
    map_tdx = load_tdx_data()
    map_api = fetch_akshare_ladder()

    all_codes = set(map_ths.keys()) | set(map_tdx.keys())
    if not all_codes and map_api: all_codes = set(map_api.keys())

    final_list = []
    for code in all_codes:
        item = {}
        if code in map_ths:
            item = map_ths[code]
        elif code in map_tdx:
            item = map_tdx[code]
        elif code in map_api:
            info = map_api[code]
            item = {'code': code, 'name': 'API', 'today_pct': 10.0, 'amount': 0,
                    'limit_days': info['limit_days'], 'tag': info['tag_api'], 'is_zt': info['is_zt']}

        if not item: continue

        if 'sina_code' not in item:
            p = "sh" if code.startswith(('6', '9')) else "sz"
            item['sina_code'] = f"{p}{code}"

        if item.get('limit_days', 0) == 0 and code in map_api:
            item['limit_days'] = map_api[code]['limit_days']
            item['is_zt'] = True
            if not item.get('tag_ths'): item['tag'] = map_api[code]['tag_api']

        if code in map_api and not map_api[code]['is_zt']:
            item['tag_extra'] = "炸板"

        final_tag = item.get('tag_ths', '')
        if not final_tag:
            t = []
            if item.get('tag_extra'): t.append(item['tag_extra'])
            if item.get('limit_days', 0) > 0:
                t.append(f"{item['limit_days']}板")
            elif item['today_pct'] > 9.8:
                t.append("首板")
            final_tag = "/".join(t)

        if item.get('tag_extra') == '炸板' and '炸板' not in final_tag:
            final_tag = f"炸板/{final_tag}"

        item['tag'] = final_tag
        final_list.append(item)

    print(f"{Fore.GREEN}✅ 数据合并完毕，共 {len(final_list)} 只标的")
    return final_list


# ================= 4. 为监控系统提供特定格式 =================
def load_history_map():
    """
    专门为 call_auction_screener.py 提供数据
    返回格式: {code: {'yest_amt': float, 'circ_mv': float, 'yest_pct': float, 'boards': int}}
    """
    # 1. 优先加载同花顺数据
    data_map = load_ths_data()
    
    # 2. 如果缺少同花顺，尝试用通信达补全 (暂略，因为同花顺通常最全)
    
    history_map = {}
    zero_turnover_count = 0
    
    for code, item in data_map.items():
        try:
            amt = item.get('amount', 0.0)
            mv = 0.0 # MVP: 同花顺导出里通常没有直接的流通市值列，或者列名不固定
            # 如果 item 中没有市值，暂时给 0，监控脚本会处理
            # 实际上 load_ths_data解析时也没有专门解析市值列，需要添加
            
            # 重新检查 load_ths_data 是否解析了市值
            # 当前 load_ths_data 确实没解析 '流通市值'，我们需要增强 load_ths_data
            pass 
        except:
            pass
            
    # 由于 load_ths_data 需要增强，我们直接在这里重新实现一个针对性的增强版加载，
    # 或者修改 load_ths_data 让其返回更多字段。
    # 考虑到 load_ths_data 被 pool_generator 使用，修改它更合理。
    pass

# 重写 load_ths_data 以支持更多字段 (如流通市值)
def load_ths_data_enhanced():
    # 复用文件查找逻辑
    if not os.path.exists(THS_DIR): return {}
    
    # ... (find file logic duplicated or reused) ...
    # 为了避免重复代码，建议把 find_file 逻辑提取，但这里为了不动太多结构，我们直接调用 enhance logic
    
    # 调用原有的文件查找逻辑 (这是私有的 logic inside load_ths_data, we should extract it or copy it)
    # Let's copy the find logic for now to be safe and independent
    files = os.listdir(THS_DIR)
    candidates = []
    for f in files:
        if f.startswith("Table") and f.endswith(".txt"):
            full_path = os.path.join(THS_DIR, f)
            date_match = re.search(r'[-_]?(20\d{6})', f)
            date_int = int(date_match.group(1)) if date_match else 0
            if f == "Table.txt":
                 candidates.append({'path': full_path, 'date': 0, 'mtime': os.path.getmtime(full_path)})
            else:
                 candidates.append({'path': full_path, 'date': date_int, 'mtime': 0})
    
    target_file = None
    if candidates:
        dated = [c for c in candidates if c['date'] > 0]
        if dated:
            dated.sort(key=lambda x: x['date'], reverse=True)
            target_file = dated[0]['path']
        else:
            candidates.sort(key=lambda x: x['mtime'], reverse=True)
            target_file = candidates[0]['path']
            
    if not target_file: return {}

    print(f"{Fore.BLUE}📂 [Data] 加载同花顺数据: {os.path.basename(target_file)}")
    
    # Robust read
    df = None
    encodings = ['gbk', 'utf-8', 'utf-16']
    for enc in encodings:
        try:
            # use header=0 usually
            df = pd.read_csv(target_file, sep=r'\t+', engine='python', encoding=enc, dtype=str)
            # Check if columns look right
            if any('代码' in c for c in df.columns):
                break
        except:
            continue
            
    if df is None:
        print(f"{Fore.RED}❌ 读取失败，尝试了 {encodings} 均无法解析")
        return {}
        
    df.columns = [c.strip() for c in df.columns]
    
    # Mapping
    col_code = next((c for c in df.columns if '代码' in c), None)
    col_amt = next((c for c in df.columns if '成交额' in c), None)
    col_mv = next((c for c in df.columns if '流通市值' in c), None)
    col_pct = next((c for c in df.columns if '涨幅' in c and '竞价' not in c and '10' not in c), None)
    col_auc_amt = next((c for c in df.columns if '早盘竞价金额' in c or '竞价金额' in c), None) # Try to find bid amount
    
    # 连板提取
    col_zt = next((c for c in df.columns if '连板' in c or '几天几板' in c), None)

    if not col_code or not col_amt:
        print(f"{Fore.RED}❌ 关键列缺失 (代码/成交额)")
        return {}
        
    res_map = {}
    cnt_zero = 0
    
    for _, row in df.iterrows():
        try:
            code = clean_code(row[col_code])
            if len(code) != 6: continue
            
            amt = safe_float(row.get(col_amt))
            mv = safe_float(row.get(col_mv))
            pct = safe_float(row.get(col_pct))
            
            boards = 0
            if col_zt:
                b_str = str(row.get(col_zt, ''))
                # 提取数字
                nums = re.findall(r'\d+', b_str)
                if nums: boards = int(nums[-1]) # 取最后一个数字 usually "3天2板" -> 2
            
            auc_amt = 0.0
            if col_auc_amt:
                auc_amt = safe_float(row.get(col_auc_amt))
            
            if amt <= 0: cnt_zero += 1
            
            res_map[code] = {
                'yest_amt': amt,
                'circ_mv': mv,
                'yest_pct': pct,
                'boards': boards,
                'yest_bid_amt': auc_amt # Yesterday's Bid Amount
            }
        except:
            continue
            
    if cnt_zero > 0:
        print(f"   ⚠️ 其中 {cnt_zero} 只标的无成交额数据")
        
    return res_map

load_history_map = load_ths_data_enhanced