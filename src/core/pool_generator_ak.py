# ==============================================================================
# 📌 策略池生成器 (Akshare 版) (src/core/pool_generator_ak.py) - 【盘后运行】
# 作用: 逻辑与 pool_generator.py 完全一致，优先使用 Akshare 数据。
# 更新内容: 同步了风险数据加载、大盘情绪JSON生成、筹码分析逻辑及LHB排序
# ==============================================================================
import pandas as pd
import os
import shutil
import sys
import re
import json
from datetime import datetime
import glob
from colorama import init, Fore

# --- 路径配置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(PROJECT_ROOT)

# 复用原有的模块
from src.core.data_loader import load_yesterday_ths_data
from src.core.market_data import MarketDataManager
from src.strategies.ddd_mode import get_ddd_pool_category
from src.strategies.f_lao_model import load_ths_history, check_fen_jue

# 尝试导入筹码分析
try:
    from src.tools.chip_analyzer import get_chip_metrics, generate_chip_tag
except ImportError:
    def get_chip_metrics(*args): return None
    def generate_chip_tag(*args): return ""

init(autoreset=True)

# 目录配置
INPUT_AK_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'akshare')
INPUT_THS_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')
RISK_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'risk')

HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')
MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')
HOLDING_STRATEGIES = {} # 可配置
LINK_DRAGON_MAP = {'002009': '002931'}
CORE_KEYWORDS = ['机器人', '航天', '军工', '卫星', '低空', 'AI', '人工智能',
                 '智能体', '算力', 'CPO', '存储', '消费电子', '华为', '信创', 
                 '数字货币', '数据要素', '文化传媒', '短剧', '多模态', '纺织', 
                 '并购重组', '固态电池', '自动驾驶']

# ================= 数据加载逻辑 (Akshare 核心) =================

def load_combined_data():
    """
    核心：加载 Akshare 数据为主，THS 数据为辅 (补充竞价金额)
    """
    # 1. 寻找最新的 Akshare market_data
    files = glob.glob(os.path.join(INPUT_AK_DIR, 'market_data_*.csv'))
    if not files:
        print(f"{Fore.RED}❌ 未找到 Akshare 数据文件! 请先运行 src/data/fetch_akshare.py")
        return []
    
    # 按文件名日期排序
    files.sort(reverse=True)
    latest_ak_file = files[0]
    print(f"{Fore.CYAN}📥 加载主数据: {os.path.basename(latest_ak_file)}")
    
    try:
        df_ak = pd.read_csv(latest_ak_file, dtype={'code': str, 'limit_days': int})
    except Exception as e:
        print(f"{Fore.RED}❌ 读取 Akshare CSV 失败: {e}")
        return []

    # 2. 寻找最新的 THS Table (用于补充竞价数据)
    ths_files = glob.glob(os.path.join(INPUT_THS_DIR, 'Table-*.txt'))
    auction_map = {}
    
    if ths_files:
        ths_files.sort(reverse=True)
        latest_ths = ths_files[0]
        print(f"{Fore.BLUE}📥 加载辅助数据 (竞价): {os.path.basename(latest_ths)}")
        
        try:
            df_ths = None
            for enc in ['gbk', 'utf-8', 'utf-16', 'gb18030']:
                try:
                    df_ths = pd.read_csv(latest_ths, sep=r'\t+', engine='python', encoding=enc, dtype=str)
                    if '代码' in df_ths.columns or '名称' in df_ths.columns:
                        break
                except: continue
            
            if df_ths is not None:
                df_ths.columns = [c.strip() for c in df_ths.columns]
                col_code = next((c for c in df_ths.columns if '代码' in c), None)
                col_bid = next((c for c in df_ths.columns if '早盘竞价金额' in c), None)
                
                if col_code and col_bid:
                    for _, row in df_ths.iterrows():
                        c = re.sub(r'\D', '', str(row[col_code])).zfill(6)
                        val = row[col_bid]
                        if pd.isna(val) or val == '--':
                            amt = 0.0
                        else:
                            s = str(val).replace('亿', '*100000000').replace('万', '*10000')
                            try: amt = eval(s)
                            except: amt = 0.0
                        auction_map[c] = amt
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ THS 数据解析失败，竞价金额将缺失: {e}")

    # 3. 转换 df_ak 为 list of dict
    all_data = []
    for _, row in df_ak.iterrows():
        code = str(row['code']).zfill(6)
        
        try:
            price = float(row['price'])
            prev_close = float(row['昨收'])
            open_price = float(row['今开'])
            high = float(row['最高'])
            low = float(row['最低'])
            pct = float(row['pct_chg'])
            
            open_pct = (open_price - prev_close) / prev_close * 100 if prev_close > 0 else 0
            max_pct = (high - prev_close) / prev_close * 100 if prev_close > 0 else 0
            min_pct = (low - prev_close) / prev_close * 100 if prev_close > 0 else 0
            
        except:
            pct = 0; open_pct = 0; max_pct = 0; min_pct = 0; price = 0
            
        limit_days = int(row.get('limit_days', 0))
        reason = str(row.get('reason', ''))
        
        # 兼容逻辑：如果 Akshare 说没板，但涨幅>9.8，尝试认为是首板
        is_zt = limit_days > 0
        if not is_zt and pct > 9.8:
            is_zt = True
            limit_days = 1

        item = {
            'code': code,
            'name': str(row['name']),
            'today_pct': pct,
            'amount': float(row['amount']),
            'turnover': float(row.get('turnover_rate', 0)),
            'circ_mv': float(row.get('circ_mv', 0)),
            'vol_ratio': float(row.get('vol_ratio', 0)),
            'price': price,
            'limit_days': limit_days,
            'is_zt': is_zt,
            'zt_reason': reason,
            'open_pct': open_pct,
            'max_pct': max_pct,
            'min_pct': min_pct,
            'call_auction_amount': auction_map.get(code, 0),
            'open_num': 0, # Akshare 暂缺炸板次数
            'is_first_limit': (limit_days == 1),
            'vol': 0,
            'vol_prev': 0,
            'pct_10': 0
        }
        all_data.append(item)
        
    return all_data

# ================= 辅助逻辑 =================

def load_text_list(filepath):
    if not os.path.exists(filepath): return {}
    mapping = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip() or line.startswith('#'): continue
            parts = line.strip().split(maxsplit=1)
            code = re.sub(r'\D', '', parts[0])
            if len(code) == 6:
                mapping[code] = parts[1] if len(parts) > 1 else "关注"
    return mapping

def load_yesterday_pool():
    # 逻辑同标准版：找昨日文件用于判断炸板反包
    if not os.path.exists(OUTPUT_DIR): return {}
    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('strategy_pool_') and f.endswith('.csv')]
    if not files and os.path.exists(ARCHIVE_DIR):
        files = [f for f in os.listdir(ARCHIVE_DIR) if f.startswith('strategy_pool_') and f.endswith('.csv')]
    
    today_str = datetime.now().strftime("%Y%m%d")
    target = None
    files.sort(reverse=True)
    
    for f in files:
        d = re.findall(r'\d{8}', f)
        if d and d[0] < today_str:
            target = f
            break
            
    if not target: return {}
    
    path = os.path.join(OUTPUT_DIR, target)
    if not os.path.exists(path): path = os.path.join(ARCHIVE_DIR, target)
    
    print(f"{Fore.MAGENTA}🔙 加载昨日池: {target}")
    res = {}
    try:
        df = pd.read_csv(path, dtype=str)
        for _, row in df.iterrows():
            if '炸板' in str(row.get('tag', '')):
                res[row['code'].zfill(6)] = {
                    'amount': float(row.get('amount', 0)),
                    'tag': str(row.get('tag', ''))
                }
    except: pass
    return res

def load_lhb_info():
    lhb_dir = os.path.join(PROJECT_ROOT, 'data', 'output', 'lhb')
    lhb_path = os.path.join(lhb_dir, 'lhb_latest.csv')
    seat_path = os.path.join(lhb_dir, 'lhb_famous_latest.csv')
    
    codes = set()
    seats = {}
    
    if os.path.exists(lhb_path):
        try:
            df = pd.read_csv(lhb_path, dtype=str)
            if '代码' in df.columns:
                codes = set(df['代码'].apply(lambda x: str(x).zfill(6)).tolist())
        except: pass
        
    if os.path.exists(seat_path):
        try:
            df = pd.read_csv(seat_path, dtype=str)
            for _, row in df.iterrows():
                label = row['游资标签']
                
                def parse_seat(val, prefix):
                    if pd.isna(val) or str(val) == 'nan': return
                    parts = str(val).split(' ')
                    for p in parts:
                        p = p.strip()
                        if not p: continue
                        name = p.split('(')[0].split('/')[0]
                        note = ""
                        if '(' in p: note = p.split('(')[1].rstrip(')')
                        
                        final_prefix = prefix
                        if "锁仓" in note or "锁仓" in p: final_prefix = "🔒"
                        elif "加仓" in note: final_prefix = "➕"
                        
                        if name not in seats: seats[name] = set()
                        seats[name].add(f"{final_prefix}{label}")

                parse_seat(row.get('买入股票'), "💰")
                parse_seat(row.get('卖出股票'), "🏃")
        except: pass
    return codes, seats

def load_risk_data():
    """加载最新的风险/异动监管数据"""
    if not os.path.exists(RISK_DIR): return {}
    files = [f for f in os.listdir(RISK_DIR) if f.startswith('risk_') and f.endswith('.csv')]
    if not files: return {}
    files.sort(reverse=True)
    target = os.path.join(RISK_DIR, files[0])
    print(f"{Fore.MAGENTA}🔎 加载风险数据: {files[0]}")
    
    risk_map = {}
    try:
        df = pd.read_csv(target)
        for _, row in df.iterrows():
            name = str(row['股票名称']).strip()
            msg = str(row.get('当前累计偏离值', ''))
            
            dev_10 = 0.0
            dev_30 = 0.0
            match = re.search(r'(-?\d+\.?\d*)%', msg)
            val = float(match.group(1)) if match else 0.0
            
            rule = str(row.get('监管规则', ''))
            if '10日' in rule: dev_10 = val
            if '30日' in rule: dev_30 = val
            
            risk_map[name] = {
                'risk_level': str(row.get('风险等级', '🟢 Safe')),
                'risk_msg': msg,
                'risk_rule': rule,
                'trigger_next': str(row.get('异动触发条件', '')),
                'deviation_val_10d': dev_10,
                'deviation_val_30d': dev_30
            }
    except Exception as e:
        print(f"⚠️ 风险数据解析失败: {e}")
    return risk_map

def calculate_market_stats(all_data, yesterday_data):
    """计算大盘情绪数据 (涨跌停家数、昨日溢价)"""
    stats = {'limit_up_count': 0, 'limit_down_count': 0, 'highest_space': 0}
    
    # 1. 统计涨跌停
    for item in all_data:
        if 'ST' in item['name'].upper(): continue
        if item['is_zt'] or item['today_pct'] > 9.8: stats['limit_up_count'] += 1
        if item['today_pct'] < -9.0: stats['limit_down_count'] += 1
        if item['limit_days'] > stats['highest_space']: stats['highest_space'] = item['limit_days']
        
    # 2. 昨日涨停溢价
    yest_zt_codes = [c for c, v in yesterday_data.items() if v.get('is_zt')]
    total_prem = 0
    valid_count = 0
    for c in yest_zt_codes:
        curr = next((x for x in all_data if x['code'] == c), None)
        if curr:
            total_prem += curr.get('open_pct', 0)
            valid_count += 1
    
    stats['yesterday_limit_up_premium'] = round(total_prem / valid_count, 2) if valid_count > 0 else 0
    return stats

def format_sina(code):
    if code.startswith('6'): return f"sh{code}"
    return f"sz{code}"

def get_link_dragon(code):
    return LINK_DRAGON_MAP.get(code, '')

def clean_manual_tag(tag, is_zt):
    if not tag: return ""
    tag = tag.replace('F佬/', '').replace('F佬', '')
    if is_zt: tag = re.sub(r'(^|/|[(])\d+板([)]|/|$)', r'\1\2', tag)
    tag = tag.replace('()', '').replace('//', '/').strip('/')
    return tag

def get_unique_concepts(base, new_con):
    if not new_con: return ""
    base_parts = set(re.split(r'[/()]', base))
    final = [c for c in new_con.split('/') if c and c not in base_parts and c not in base]
    return "/".join(final)

def get_core_concepts(name, tag):
    text = f"{name} {tag}"
    found = [k for k in CORE_KEYWORDS if k in text]
    return "/".join(found)

def check_special_shape(item):
    if item['is_zt']:
        open_pct = item['open_pct']
        if open_pct > 9.0: return [], "一字" if item.get('open_num',0)==0 else "T字"
        return [], "换手板"
    return [], ""

# ================= 主生成逻辑 =================

def run_generator():
    all_data = load_combined_data()
    if not all_data: return

    holdings = load_text_list(HOLDINGS_PATH)
    flao = load_text_list(F_LAO_PATH)
    manual = load_text_list(MANUAL_FOCUS_PATH)
    broken_map = load_yesterday_pool()
    lhb_codes, lhb_seats = load_lhb_info()
    risk_map = load_risk_data() # 新增：风险数据
    
    # Yesterday full for Ratio
    yest_full = load_yesterday_ths_data()
    
    # History for FenJue
    history_map = load_ths_history(INPUT_THS_DIR, days=5)

    # Market Stats (New)
    print(f"{Fore.MAGENTA}📊 计算大盘情绪数据...")
    dapan_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'dapan')
    md_manager = MarketDataManager(dapan_dir)
    market_loaded = md_manager.load_data()
    market_stats = calculate_market_stats(all_data, yest_full)
    
    print(f"{Fore.GREEN}📋 启动生成 (Akshare Mode) | 股票: {len(all_data)} | 持仓: {len(holdings)} | 关注: {len(flao)}")
    
    pool = []
    
    for item in all_data:
        code = item['code']
        name = item['name']
        
        if 'ST' in name.upper(): continue
        
        is_selected = False
        tags = []
        is_zt = item['is_zt']
        
        # 1. 涨停
        if is_zt:
            is_selected = True
            days = item['limit_days']
            tags.append(f"{days}板" if days > 1 else "首板")
        else:
            if item['max_pct'] > 9.5 and item['today_pct'] < 9.5:
                # 简单判断炸板
                pass

        # 2. 身份
        cleaned_manual = ""
        if code in holdings:
            is_selected = True
            tags.append(f"持仓/{name}")
        elif code in flao:
            is_selected = True
            note = clean_manual_tag(flao[code], is_zt)
            t = f"F佬/{note}" if note != "关注" else "F佬/关注"
            tags.append(t)
            cleaned_manual = t
            
        # 3. LHB (Sort Logic added)
        if code in lhb_codes:
            is_selected = True
            tags.append("🐉龙虎榜")
        if name in lhb_seats:
            is_selected = True
            def sort_key(t):
                if "🔒" in t or "➕" in t: return 0
                if "💰" in t: return 1
                return 2
            tags.extend(sorted(list(lhb_seats[name]), key=sort_key))
            
        # 4. 人气
        is_pop = False
        if code in manual or name in manual: is_pop = True
        if item['limit_days'] >= 3: is_pop = True
        if item['amount'] > 20_0000_0000: # 20亿
            is_pop = True
            tags.append("成交")
        if is_pop:
            is_selected = True
            tags.append("★人气")
            
        # 5. 断板反包
        if code in broken_map and item['today_pct'] > 0:
            is_selected = True
            t = "🔥A大焚诀"
            yest_amt = broken_map[code]['amount']
            if item['amount'] > yest_amt and yest_amt > 1000:
                t += "/爆量"
            tags.append(t)
            
        # 6. DDD
        ddd_tag = get_ddd_pool_category(item)
        if ddd_tag:
            is_selected = True
            tags.append(ddd_tag)
            
        # 7. Fen Jue
        if code in history_map:
             f_tags = check_fen_jue(history_map[code])
             if f_tags: 
                 tags.extend(f_tags)
                 is_selected = True

        # --- 筹码分析 (同步标准版逻辑) ---
        # 触发条件：持仓 OR 昨日炸板 OR 高标(>=3板)
        should_analyze_chips = (code in holdings) or (code in broken_map) or (item['limit_days'] >= 3)
        if is_selected and should_analyze_chips:
            met = get_chip_metrics(code)
            if met:
                 ct = generate_chip_tag(met)
                 if ct: tags.append(ct)

        if is_selected:
            # Concepts
            core = get_core_concepts(name, str(item.get('zt_reason', '')))
            uniq = get_unique_concepts(cleaned_manual, core)
            
            # Special Shapes
            _, zt_type = check_special_shape(item)
            if zt_type: tags.append(f"[{zt_type}]")
            
            # Ratio
            y_amt = 0
            if yest_full and code in yest_full: y_amt = yest_full[code].get('amount', 0)
            ratio = 0
            if y_amt > 0: ratio = item['call_auction_amount'] / y_amt
            item['call_auction_ratio'] = round(ratio, 3)
            
            final_tags = []
            final_tags.extend(tags)
            if uniq: final_tags.append(uniq)
            
            # Dedupe
            seen = set()
            clean = []
            for x in final_tags:
                if x not in seen:
                    clean.append(x)
                    seen.add(x)
            
            # Risk Merge
            risk_info = risk_map.get(name, {
                'risk_level': '🟢 Safe', 'risk_msg': '-', 'trigger_next': '-', 'risk_rule': '-',
                'deviation_val_10d': 0.0, 'deviation_val_30d': 0.0
            })
            
            row = {
                'sina_code': format_sina(code),
                'name': name,
                'tag': "/".join(clean).replace('//', '/'),
                'amount': item['amount'],
                'last_amount': y_amt,
                'today_pct': item['today_pct'],
                'turnover': item['turnover'],
                'open_pct': item['open_pct'],
                'price': item['price'],
                'link_dragon': get_link_dragon(code),
                'vol_ratio': item['vol_ratio'],
                'code': code,
                'call_auction_ratio': item['call_auction_ratio'],
                'limit_up_type': zt_type,
                # Risk Data
                'risk_level': risk_info['risk_level'],
                'risk_msg': risk_info['risk_msg'],
                'risk_rule': risk_info['risk_rule'],
                'trigger_next': risk_info['trigger_next'],
                'deviation_val_10d': risk_info['deviation_val_10d'],
                'deviation_val_30d': risk_info['deviation_val_30d']
            }
            pool.append(row)
            
    # Export
    today_str = datetime.now().strftime("%Y%m%d")
    out_file = os.path.join(OUTPUT_DIR, f'strategy_pool_{today_str}.csv')
    
    if pool:
        df_out = pd.DataFrame(pool)
        df_out.sort_values(by='amount', ascending=False, inplace=True)
        # Columns ordering
        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 
                'risk_level', 'risk_msg', 'trigger_next', 'risk_rule', 'deviation_val_10d', 'deviation_val_30d',
                'call_auction_ratio', 'last_amount', 'limit_up_type', 'vol_ratio', 'link_dragon', 'code']
        # Filter existing cols
        final_cols = [c for c in cols if c in df_out.columns]
        df_out = df_out[final_cols]
        
        df_out.to_csv(out_file, index=False, encoding='utf-8-sig')
        # Copy to generic name
        shutil.copyfile(out_file, os.path.join(OUTPUT_DIR, 'strategy_pool.csv'))
        
        print(f"{Fore.GREEN}✅ 策略池生成完毕: {out_file} ({len(pool)}只)")
        
        # Archive
        if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
        shutil.copy2(out_file, os.path.join(ARCHIVE_DIR, f'strategy_pool_{today_str}.csv'))
        
        # --- Export Market Sentiment JSON (新增) ---
        if market_loaded:
            market_json_path = os.path.join(OUTPUT_DIR, f'market_sentiment_{today_str}.json')
            try:
                final_json = md_manager.get_summary()
                final_json.update(market_stats)
                with open(market_json_path, 'w', encoding='utf-8') as f:
                    json.dump(final_json, f, indent=2, ensure_ascii=False)
                print(f"📄 大盘数据: {market_json_path}")
            except Exception as e:
                print(f"❌ 导出大盘JSON失败: {e}")
                
    else:
        print("⚠️ 未生任何标的")

if __name__ == '__main__':
    run_generator()