# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py) - 【竞价运行】
# v12.0 全自动实盘版 - (Table.txt做底库 + Akshare实时抓取)
# Last Modified: 2026-01-11
# ==============================================================================
import pandas as pd
import akshare as ak
import os
import re
import sys
import time
import datetime
from colorama import init, Fore, Style, Back

# 解决 Windows 终端输出编码问题
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# Append PROJECT_ROOT to sys.path to allow imports from src
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import load_holdings, HOLDINGS_PATH

# 静态底库目录
THS_DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')
MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')

# 引入情绪周期
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
try:
    from emotion_cycle import EmotionalCycleEngine
except ImportError:
    # Fallback mock
    class EmotionalCycleEngine:
        def __init__(self): pass
        def get_current_phase(self): return "Rising"

def clean_code(val):
    """统一为6位数字代码"""
    return re.sub(r'\D', '', str(val)).zfill(6)

# ================= 1. 加载历史底库 (使用统一模块) =================
# 动态引入，兼容路径
try:
    from src.core.data_loader import load_history_map
except ImportError:
    # 尝试调整 path
    sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
    sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
    from data_loader import load_history_map

# [新增] 引入 DDD 策略模块
try:
    from src.strategies.ddd_mode import check_ddd_strategy
except ImportError:
    sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'strategies'))
    from ddd_mode import check_ddd_strategy

def load_history_data():
    """Wrapper specifically for this script's display messages"""
    print(f"{Fore.CYAN}📂 [1/3] 正在加载静态底库 (昨收数据 - 统一模块)...{Style.RESET_ALL}")
    data = load_history_map()
    if not data:
        print(f"{Fore.RED}❌ 底库加载失败，请检查 data/input/ths 下的文件{Style.RESET_ALL}")
    else:
        print(f"✅ 底库加载完成，共 {len(data)} 只标的")
    return data


# ================= [新增] 获取板块数据的辅助函数 =================
def get_sector_map():
    """
    获取全市场实时板块涨幅数据
    返回: dict { '行业名称': 涨跌幅%, ... }
    """
    print(f"{Fore.CYAN}📡 [2.5/3] 正在获取板块热度数据 (用于共振分析)...{Style.RESET_ALL}")
    sector_map = {}
    try:
        # 1. 获取行业板块
        df_bk = ak.stock_board_industry_name_em()
        for _, row in df_bk.iterrows():
            name = row['板块名称']
            pct = float(row['涨跌幅'])
            sector_map[name] = pct

        # 2. 获取概念板块 (补充热门概念如AI、卫星等)
        # 注意：概念板块数据量大，只取涨幅前 50 的热门概念，提高效率
        df_con = ak.stock_board_concept_name_em()
        df_con = df_con.sort_values(by='涨跌幅', ascending=False).head(100)
        for _, row in df_con.iterrows():
            name = row['板块名称']
            pct = float(row['涨跌幅'])
            sector_map[name] = pct

        print(f"✅ 板块情绪加载完成，捕捉到 {len(sector_map)} 个热点方向")
        return sector_map
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 板块数据获取略过 (不影响个股): {e}{Style.RESET_ALL}")
        return {}


# ================= 2. 获取实时数据 (Akshare + 本地文件优先) =================
def load_call_auction_data_from_file():
    """
    尝试从 data/input/call_auction/ 读取最新的同花顺导出文件
    使用手动行解析模式，以最大程度兼容 '复制粘贴' 产生的混乱分隔符
    """
    base_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'call_auction')
    if not os.path.exists(base_dir): return None
    
    files = [f for f in os.listdir(base_dir) if f.lower().endswith(('.txt', '.csv', '.xls', '.xlsx'))]
    if not files: return None
    
    # Sort by mtime
    files.sort(key=lambda x: os.path.getmtime(os.path.join(base_dir, x)), reverse=True)
    latest_file = files[0]
    file_path = os.path.join(base_dir, latest_file)
    
    print(f"{Fore.CYAN}📂 [2A/3] 检测到本地竞价文件: {latest_file}，优先加载...{Style.RESET_ALL}")
    
    # 1. Read Content
    content = ""
    try:
        with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
    except:
        try:
            with open(file_path, 'r', encoding='gbk') as f: content = f.read()
        except Exception as e:
            print(f"{Fore.RED}❌ 无法读取文件: {e}{Style.RESET_ALL}")
            return None
            
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    # 2. Find Header
    header_idx = -1
    header_parts = []
    for i, line in enumerate(lines[:20]): # Scan first 20 lines
        if "代码" in line and ("名称" in line or "涨幅" in line):
            header_idx = i
            header_parts = line.split() # Split by ANY whitespace
            break
            
    if header_idx == -1: 
        print(f"{Fore.RED}❌ 未找到表头行 (需包含 '代码'){Style.RESET_ALL}")
        return None

    # 3. Map Columns
    idx_code = -1
    idx_name = -1
    idx_amt = -1
    idx_pct = -1
    
    for i, h in enumerate(header_parts):
        if "代码" in h: idx_code = i
        if "名称" in h: idx_name = i
        if h in ["竞价金额", "竞价额", "早盘竞价金额"]: idx_amt = i
        if h in ["竞价涨幅", "竞价涨幅%"]: idx_pct = i
        
    # Lazy Match for amount/pct if not precise
    if idx_amt == -1:
        for i, h in enumerate(header_parts):
            if "竞价金额" in h: idx_amt = i; break
            
    if idx_code == -1 or idx_amt == -1:
        print(f"{Fore.RED}❌ 缺少关键列: CodeIdx={idx_code}, AmtIdx={idx_amt}{Style.RESET_ALL}")
        print(f"Header: {header_parts}")
        return None

    # 4. Parse Rows
    res_map = {}
    
    # Helper: Parse Wan/Yi
    def parse_wan(x):
        try:
            if not x or x == '--': return 0.0
            s = str(x).replace('亿', '*10000').replace('万', '').replace(' ', '').replace(',', '')
            if '亿' in str(x): return eval(s)
            return float(s)
        except: return 0.0

    print(f"正在解析数据，表头长度: {len(header_parts)}")
    
    for line in lines[header_idx+1:]:
        parts = line.split()
        if len(parts) < max(idx_code, idx_amt) + 1: continue
        
        try:
            # Code
            raw_code = parts[idx_code]
            code = re.sub(r"\D", "", raw_code).zfill(6)
            
            # Name
            name = "未知"
            if idx_name != -1 and len(parts) > idx_name:
                name = parts[idx_name]
                
            # Amt
            raw_amt = parts[idx_amt]
            # Smart fix: if parts split incorrectly due to spaces in name?
            # Usually stock names don't have spaces.
            
            auc_val = 0.0
            # If raw_amt is a large integer string "4084080" -> it is Yuan.
            # If it is "1.5亿" -> parse_wan -> 15000 Wan.
            
            if raw_amt.replace('.','').isdigit():
                 # Pure number, assume Yuan if > 100000? 
                 # Or verify unit.
                 # User data: 4084080. This is 408 Wan.
                 # So pure number = Yuan.
                 auc_val = float(raw_amt) / 10000.0
            else:
                 auc_val = parse_wan(raw_amt)
                 
            # Pct
            pct_val = 0.0
            if idx_pct != -1 and len(parts) > idx_pct:
                raw_pct = parts[idx_pct]
                try:
                    pct_val = float(str(raw_pct).replace('%', '').replace('+', ''))
                except: pass
            
            res_map[code] = {
                'code': code,
                'name': name,
                'auc_amt': auc_val,
                'open_pct': pct_val
            }
        except: continue

    if res_map:
        print(f"✅ 从本地文件加载了 {len(res_map)} 条竞价数据")
        return pd.DataFrame(res_map.values())
        
    return None

def get_live_data():
    # 1. Try Local File First
    local_df = load_call_auction_data_from_file()
    if local_df is not None and not local_df.empty:
        return local_df

    print(f"{Fore.CYAN}📡 [2B/3] 未找到本地文件，正在请求 Akshare 实时行情 (全市场)...{Style.RESET_ALL}")
    start_time = time.time()

    try:
        # 获取A股实时行情：包含 代码, 名称, 最新价, 涨跌幅, 成交额(即竞价金额)
        # 注意：9:25-9:30期间，'成交额'字段即为'竞价成交额'
        df = ak.stock_zh_a_spot_em()

        # 映射列名
        # Akshare 返回列通常为: 序号, 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, ...
        # 我们需要：代码, 名称, 涨跌幅(作为竞价涨幅), 成交额(作为竞价金额)

        # 重命名方便处理
        rename_map = {
            '代码': 'code',
            '名称': 'name',
            '涨跌幅': 'open_pct',
            '成交额': 'auc_amt',
            '最新价': 'current_price'
        }
        df = df.rename(columns=rename_map)

        # 简单清洗
        df['code'] = df['code'].astype(str)

        # 过滤掉退市或无数据
        df = df[df['open_pct'].notnull()]

        print(f"✅ 实时数据获取成功，耗时 {time.time() - start_time:.2f}秒，共 {len(df)} 条")
        return df
    except Exception as e:
        print(f"{Fore.RED}❌ Akshare 接口请求失败: {e}{Style.RESET_ALL}")
        print("请检查网络连接或 Akshare 版本 (pip install --upgrade akshare)")
        return pd.DataFrame()



# ================= 1.5 加载策略池 (重点关注) =================
def load_strategy_pool():
    """加载 strategy_pool.csv 用于高亮显示"""
    pool_path = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
    if not os.path.exists(pool_path): return {}
    
    pool_map = {}
    try:
        df = pd.read_csv(pool_path)
        for _, row in df.iterrows():
            # 兼容 akshare code (6位) 和 sina code (sz000001)
            code = str(row.get('sina_code', ''))[2:] 
            if not code: code = str(row.get('code', '')).zfill(6)
            
            tag = str(row.get('tag', ''))
            pool_map[code] = tag
    except Exception as e:
        print(f"⚠️ 策略池加载失败: {e}")
        
    print(f"✅ 策略池加载完成: {len(pool_map)} 只")
    return pool_map

def load_manual_focus():
    """加载手动关注列表"""
    if not os.path.exists(MANUAL_FOCUS_PATH): return set()
    s = set()
    try:
        with open(MANUAL_FOCUS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'): continue
            # 提取数字或中文
            parts = line.split()
            for p in parts:
                if p.isdigit(): s.add(p.zfill(6))
                else: s.add(p) # 可能是名称
    except:
        pass
    print(f"✅ 手动关注加载完成: {len(s)} 个")
    return s


# ================= 3. 策略判定 (核心升级版) =================
def analyze_stock(row, history_info, pool_map, phase, sector_map=None):
    """
    row: 实时数据 (Akshare)
    history_info: 静态数据 (Table.txt)
    pool_map: 策略池数据
    phase: 市场情绪周期
    sector_map: [新] 板块涨跌幅字典
    """
    code = row['code']
    name = row['name']

    # 1. 获取实时数据
    try:
        open_pct = float(row['open_pct'])
        auc_amt = float(row['auc_amt'])  # 竞价金额
    except:
        return None

    # 2. 获取历史数据
    if code not in history_info: return None
    info = history_info[code]

    yest_amt = info['yest_amt']
    circ_mv = info['circ_mv']
    yest_pct = info['yest_pct']
    boards = info['boards']
    # 尝试获取行业，如果没有则显示未知
    industry = info.get('industry', '未知')

    if yest_amt == 0 or circ_mv == 0: return None

    # 3. 计算核心指标
    ratio_yest = (auc_amt / yest_amt * 100)
    ratio_mv = (auc_amt / circ_mv * 100)

    # 4. --- [新增] 板块共振判定逻辑 ---
    sector_pct = 0.0
    sector_display = industry  # 默认显示行业名
    is_sector_hot = False  # 板块是否热点
    is_sector_weak = False  # 板块是否拖后腿

    if sector_map and industry in sector_map:
        sector_pct = sector_map[industry]

        # 判定标准: 涨幅 > 1.5% 算热点， < -0.5% 算弱势
        if sector_pct >= 1.5:
            is_sector_hot = True
            sector_display = f"{Fore.RED}🔥{industry}:{sector_pct:.1f}%{Style.RESET_ALL}"
        elif sector_pct < -0.5:
            is_sector_weak = True
            sector_display = f"{Fore.GREEN}❄️{industry}:{sector_pct:.1f}%{Style.RESET_ALL}"
        else:
            sector_display = f"{industry}:{sector_pct:.1f}%"

    # 5. 策略打分系统
    score = 60
    decision = "观察"
    fail_msg = ""
    is_qualified = False
    is_weak_to_strong = False  # 弱转强标记

    # --- 基础过滤 ---
    min_auc = 300_0000
    if code in pool_map: min_auc = 0
    if auc_amt < min_auc: return None

    # 一字板处理
    if open_pct > 9.8:
        score = 0
        if code in pool_map: score = 90
        return {
            'code': code, 'name': name, 'score': score, 'decision': f"{Fore.BLUE}一字板{Style.RESET_ALL}",
            'open_pct': open_pct, 'auc': auc_amt, 'yest_pct': yest_pct, 'boards': boards,
            'r_mv': ratio_mv, 'circ_mv': circ_mv, 'sector_info': sector_display
        }

    # --- [新增] DDD 策略兼容 ---
    ddd_score, ddd_dec, ddd_tag = check_ddd_strategy(row, history_info[code])
    if ddd_score > 0:
        score = ddd_score
        decision = ddd_dec
        if code in pool_map: score += 5
        # 如果板块也强，DDD策略再加分
        if is_sector_hot:
            score += 5
            decision += " 共振"

        # Append DDD detail info
        decision += f" [{ddd_tag}]"


        return {
            'code': code, 'name': name, 'score': score, 'decision': decision,
            'open_pct': open_pct, 'auc': auc_amt, 'r_yest': ratio_yest,
            'r_mv': ratio_mv, 'yest_pct': yest_pct, 'boards': boards,
            'circ_mv': circ_mv, 'tag': pool_map.get(code, ""), 'sector_info': sector_display
        }

    # --- 核心策略逻辑 (F佬/A大) ---
    pool_tag = pool_map.get(code, "")

    # A. 深水低吸
    if open_pct <= -5.0:
        if "低吸" in pool_tag or "趋势" in pool_tag or "F佬" in pool_tag:
            decision = f"{Fore.GREEN}✅ 深水低吸{Style.RESET_ALL}"
            score = 88
        else:
            fail_msg = f"深水({open_pct}%)"

    # B. A大焚诀 (核心)
    elif "A大焚诀" in pool_tag or "F佬" in pool_tag:
        if open_pct > 0:
            is_weak_to_strong = True
            decision = f"{Fore.RED}🔥 A大反包{Style.RESET_ALL}"
            score = 90

            # [核心优化] 板块共振加分
            if is_sector_hot:
                score = 98  # 满分信号
                decision += f" {Back.RED}{Fore.WHITE}共振{Style.RESET_ALL}"
            elif is_sector_weak:
                score -= 15  # 降分
                decision += f" {Fore.YELLOW}⚠️孤狼{Style.RESET_ALL}"

            if ratio_mv > 1.0:
                decision += "/爆量"
                score += 2
        else:
            fail_msg = f"未翻红({open_pct}%)"
            score = 50
            decision = f"{Fore.YELLOW}等待翻红{Style.RESET_ALL}"
            fail_msg = ""

            # C. 常规弱转强
    elif open_pct < 3.0:
        if ratio_mv > 0.8:
            is_weak_to_strong = True
            decision = f"{Fore.MAGENTA}★ 弱转强{Style.RESET_ALL}"
            # 板块加成
            if is_sector_hot:
                score += 10
                decision += f"/{industry}强"
        else:
            if not pool_tag: fail_msg = f"竞价弱({open_pct}%)"

    # D. 高开风险
    else:
        if open_pct > 5.0 and open_pct < 9.8:
            if "加速" in pool_tag or is_sector_hot:  # 如果板块热，高开也可以接受
                pass
            else:
                decision = f"{Fore.YELLOW}⚠️ 高开风险{Style.RESET_ALL}"
                score = 60

    # --- 最终组装 ---
    in_pool_mark = ""
    if code in pool_map:
        if score < 80: score += 10
        in_pool_mark = f"{Back.MAGENTA}{Fore.WHITE} 池 {Style.RESET_ALL}"
        if fail_msg:
            decision = f"{Fore.YELLOW}{fail_msg}{Style.RESET_ALL}"
            score = 70
            fail_msg = ""

    if fail_msg: return None  # 过滤掉不符合的

    decision += in_pool_mark

    return {
        'code': code,
        'name': name,
        'score': score,
        'decision': decision,
        'open_pct': open_pct,
        'auc': auc_amt,
        'r_yest': ratio_yest,
        'r_mv': ratio_mv,
        'yest_pct': yest_pct,
        'boards': boards,
        'circ_mv': circ_mv,
        'tag': pool_tag,
        'sector_info': sector_display  # [新]
    }


# ================= 🚀 主程序 =================
def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (Akshare Plus版) {Style.RESET_ALL}")
    print("=" * 120)

    # 0. 情绪周期 (Mock)
    current_phase = "Rising"
    print(f"{Fore.CYAN}🌊 [0/4] 正在分析情绪周期... {Fore.MAGENTA}{current_phase}{Style.RESET_ALL}")

    # 1. 加载数据
    history_map = load_history_data()
    if not history_map: return
    pool_map = load_strategy_pool()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    valid_codes = set(pool_map.keys()) | set(holdings.keys())
    for item in manual_focus:
        if item.isdigit(): valid_codes.add(item)

    # 2. 获取实时数据
    live_df = get_live_data()
    if live_df.empty: return

    # 2.5 [新增] 获取板块数据
    sector_map = get_sector_map()

    print(f"{Fore.CYAN}⚙️ [3/3] 正在进行策略计算 (含板块共振分析)...{Style.RESET_ALL}")
    print(f"🎯 过滤范围: 持仓 {len(holdings)} + 策略 {len(pool_map)} + 手动 {len(manual_focus)}")

    results = []
    seen_codes = set()

    for _, row in live_df.iterrows():
        code = clean_code(row['code'])
        if code in seen_codes: continue
        seen_codes.add(code)

        # 过滤
        is_target = False
        if code in valid_codes: is_target = True
        if not is_target and str(row['name']) in manual_focus: is_target = True
        if not is_target: continue

        # 核心分析
        res = analyze_stock(row, history_map, pool_map, current_phase, sector_map)
        if res:
            results.append(res)

    # 3. 排序与展示
    results.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print("\n" + "=" * 125)
    print(
        f"📊 实时监控报告 | 时间: {datetime.datetime.now().strftime('%H:%M:%S')} | 扫描: {len(live_df)} | 命中: {len(results)}")
    # [新增] 这里增加了 '板块情况' 列
    print(f"{'代码':<8} {'名称':<8} {'竞价%':<8} {'今/昨%':<12} {'连板':<6} {'市值':<8} {'板块情况':<18} {'AI决策'}")
    print("-" * 125)

    count = 0
    for item in results:
        if item['score'] < 40: continue  # 过滤低分

        count += 1
        auc_str = f"{int(item['auc'] / 10000)}万"

        # 格式化数据
        yest_pct = item.get('yest_pct', 0)
        c_yest = Fore.RED if yest_pct > 0 else Fore.GREEN
        c_open = Fore.RED if item['open_pct'] > 0 else Fore.GREEN

        boards = item.get('boards', 0)
        boards_str = f"{Fore.RED}{boards}板{Style.RESET_ALL}" if boards >= 2 else ""

        mv_str = f"{item.get('circ_mv', 0) / 100000000:.1f}亿"

        # 决策显示
        decision_display = item['decision']

        # 打印行
        print(
            f"{item['code']:<8} "
            f"{item['name'][:4]:<8} "
            f"{c_open}{item['open_pct']:>5.2f}{Style.RESET_ALL}/"
            f"{c_yest}{yest_pct:<5.1f}{Style.RESET_ALL} "
            f"{boards_str:<6} "
            f"{mv_str:<8} "
            f"{item.get('sector_info', ''):<26} "  # [新增] 板块列，预留足够宽度
            f"{decision_display} "
            f"额:{auc_str}"
        )

    if count == 0:
        print(f"{Fore.YELLOW}暂无符合【严格标准】的标的，请稍候再试...{Style.RESET_ALL}")
    print("=" * 125)


if __name__ == "__main__":
    # 检查当前时间，如果在9:25之前提醒用户
    now = datetime.datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute < 25):
        print(f"{Fore.YELLOW}⚠️ 提示：当前时间早于 9:25，Akshare 获取的成交额可能不是最终竞价金额。{Style.RESET_ALL}")

    main()