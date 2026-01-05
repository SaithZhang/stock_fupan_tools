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
    target_file = os.path.join(THS_DIR, 'Table.txt')
    if not os.path.exists(target_file):
        target_file = find_latest_file(THS_DIR)

    if not target_file: return {}

    print(f"{Fore.BLUE}📂 [优先] 加载同花顺数据: {os.path.basename(target_file)}")
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
        col_pct = next((c for c in df.columns if '涨幅' in c and '竞价' not in c and '10' not in c and '3' not in c),
                       None)
        col_amt = next((c for c in df.columns if '成交额' in c), None)
        col_to = next((c for c in df.columns if '换手' in c), None)

        col_zt_days = next((c for c in df.columns if '连续涨停' in c or '连板' in c), None)
        col_reason = next((c for c in df.columns if '原因' in c), None)
        col_desc = next((c for c in df.columns if '几天几板' in c), None)
        col_pct10 = next((c for c in df.columns if '10日涨幅' in c), None)
        col_auc_pct = next((c for c in df.columns if '竞价涨幅' in c), None)

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
            # 如果涨幅 > 60 (A股不太可能，除非新股首日)，或者名字里有%，说明读错了
            if abs(pct) > 60 and 'N' not in name and 'C' not in name:
                # 可能是错位了，尝试修正或置0
                pct = 0.0
            if '%' in name or len(name) > 10:
                # 名字列读到了垃圾数据
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
            }

            item['limit_days'] = int(safe_float(row.get(col_zt_days, 0)))
            item['is_zt'] = (item['limit_days'] > 0 and item['today_pct'] > 0) or (item['today_pct'] > 9.8)

            tags = []
            desc = safe_str(row.get(col_desc))
            if desc and len(desc) < 20: tags.append(desc)  # 防止把长文本读进来

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