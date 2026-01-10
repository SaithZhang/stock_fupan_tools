# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py)
# v12.0 全自动实盘版 - (Table.txt做底库 + Akshare实时抓取)
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
    from data_loader import load_history_map

def load_history_data():
    """Wrapper specifically for this script's display messages"""
    print(f"{Fore.CYAN}📂 [1/3] 正在加载静态底库 (昨收数据 - 统一模块)...{Style.RESET_ALL}")
    data = load_history_map()
    if not data:
        print(f"{Fore.RED}❌ 底库加载失败，请检查 data/input/ths 下的文件{Style.RESET_ALL}")
    else:
        print(f"✅ 底库加载完成，共 {len(data)} 只标的")
    return data


# ================= 2. 获取实时数据 (Akshare) =================
def get_live_data():
    print(f"{Fore.CYAN}📡 [2/3] 正在请求 Akshare 实时行情 (全市场)...{Style.RESET_ALL}")
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

# ================= 3. 策略判定 (核心) =================
def analyze_stock(row, history_info, pool_map, phase):
    """
    row: 实时数据 (Akshare)
    history_info: 静态数据 (Table.txt)
    pool_map: 策略池数据
    phase: 市场情绪周期 (Rising, Decline, etc.)
    """
    code = row['code']
    name = row['name']

    # 1. 获取实时数据
    try:
        open_pct = float(row['open_pct'])
        auc_amt = float(row['auc_amt'])  # 9:25时的成交额 = 竞价金额
    except:
        return None

    # 2. 获取历史数据 (分母)
    if code not in history_info: return None

    yest_amt = history_info[code]['yest_amt']
    circ_mv = history_info[code]['circ_mv']
    yest_pct = history_info[code]['yest_pct']
    boards = history_info[code]['boards']

    if yest_amt == 0 or circ_mv == 0: return None

    # 3. 计算指标
    ratio_yest = (auc_amt / yest_amt * 100)
    ratio_mv = (auc_amt / circ_mv * 100)

    # 4. 策略逻辑 (F佬 v10.0 精准版 + 情绪周期 + 策略池)
    score = 60
    decision = "观察"
    fail_msg = ""
    is_qualified = False
    is_weak_to_strong = False  # 弱转强标记
    
    # --- 周期动态阈值 ---
    # 默认标准
    WTS_OPEN_MIN = -5.0   # 弱转强最低开盘
    WTS_OPEN_MAX = 1.8    # 弱转强最高开盘
    WTS_MV_RATIO = 0.8    # 弱转强市值比门槛
    WTS_DEEP_RATIO = 1.0  # 深水区市值比门槛

    if phase == "Decline" or phase == "Ice Point":
        # 退潮期：更严格
        WTS_OPEN_MAX = 0.5    # 只能接受平盘以下转强
        WTS_MV_RATIO = 1.2    # 需要更大更主动的量
        WTS_DEEP_RATIO = 1.5
    elif phase == "Rising" or phase == "High Tide":
        # 上升期：宽松
        WTS_OPEN_MAX = 3.0    # 甚至小高开也能接
        WTS_MV_RATIO = 0.6    # 只要有量就行

    # --- 规则0: 基础过滤 (池内票放宽) ---
    min_auc = 300_0000
    if code in pool_map: min_auc = 0 # 池内票完全不过滤金额
    
    if auc_amt < min_auc: return None
    if open_pct > 9.8: 
        # 如果是池内票，一字板也给高分显示
        score = 0
        if code in pool_map:
            score = 90
        
        return {
            'code': code, 'name': name, 'score': score, 'decision': f"{Fore.BLUE}一字板{Style.RESET_ALL}", 
            'open_pct': open_pct, 'auc': auc_amt, 'yest_pct': yest_pct, 'boards': boards, 
            'r_mv': ratio_mv, 'circ_mv': circ_mv
        }

    # --- 规则1: 竞价涨幅 (含弱转强) ---
    if open_pct < -2.0:
        # 深水区
        if ratio_mv > WTS_DEEP_RATIO:
            is_weak_to_strong = True
        else:
            fail_msg = f"低开({open_pct}%)"
    elif open_pct < WTS_OPEN_MAX:
        # 平盘/小红盘区
        if ratio_mv > WTS_MV_RATIO:
            is_weak_to_strong = True
        else:
            fail_msg = f"竞价弱({open_pct}%)"
    else:
        # 高开区 (非弱转强，属于强更强)
        # 如果是池内票，高开也值得看
        pass

    # --- 规则2: 竞价/昨成交 ---
    if ratio_yest < 3.0:
        if not is_weak_to_strong and code not in pool_map:
            fail_msg = f"承接弱({ratio_yest:.1f}%)"
    elif ratio_yest > 25.0: # 稍微放宽防止过热误杀
        if not is_weak_to_strong:
            pass # 过热

    # --- 规则3: 市值分层 (池内票可忽略) ---
    if code not in pool_map:
        mv_yi = circ_mv / 100000000.0
        limit = 0.82
        if mv_yi < 20.0: limit = 0.95
        elif 20.0 <= mv_yi < 27.0: limit = 0.78
        
        if ratio_mv < limit and not is_weak_to_strong:
             fail_msg = f"量不足({ratio_mv:.2f}%)"

    # --- 结论 ---
    in_pool_mark = ""
    tag_info = "" # 存储具体标签
    
    if code in pool_map:
        score += 20
        in_pool_mark = f"{Back.MAGENTA}{Fore.WHITE} 池 {Style.RESET_ALL}"
        tag_info = pool_map[code] # 获取具体标签 (如 '🔥焚诀')
        
        # 池内票，即使 fail_msg 也可以保留显示，但分低
        if fail_msg: 
             decision = f"{Fore.YELLOW}{fail_msg}{Style.RESET_ALL}"
             score = 70
             fail_msg = "" # 清空 fail_msg 以便返回结果

    if fail_msg:
        return {
            'code': code, 'name': name, 'score': 40, 'decision': fail_msg, 
            'open_pct': open_pct, 'auc': auc_amt, 'r_yest': ratio_yest, 'r_mv': ratio_mv,
            'yest_pct': yest_pct, 'boards': boards, 'circ_mv': circ_mv, 'tag': tag_info
        }

    # 成功入选
    if is_weak_to_strong:
        decision = f"{Fore.MAGENTA}★ 弱转强{Style.RESET_ALL}"
        score = 85 + (10 if code in pool_map else 0)
    else:
        decision = f"{Fore.RED}★ 达标关注{Style.RESET_ALL}"
        score = 80 + (10 if code in pool_map else 0)

    # 完美模型
    if open_pct > 2.0 and 5.0 <= ratio_yest <= 15.0:
        decision = f"{Back.RED}{Fore.WHITE} 🔥 完美 {Style.RESET_ALL}"
        score = 95 + (10 if code in pool_map else 0)
        
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
        'tag': tag_info
    }


# ================= 🚀 主程序 =================
def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (Akshare版) {Style.RESET_ALL}")
    print("=" * 100)
    
    # 0. 获取当前周期
    print(f"{Fore.CYAN}🌊 [0/4] 正在分析情绪周期...{Style.RESET_ALL}")
    try:
        cycle_engine = EmotionalCycleEngine()
        cycle_engine.analyze_historical_cycle(days=30)
        current_phase = cycle_engine.get_current_phase()
    except:
        current_phase = "Rising" # 默认
        
    print(f"   当前周期判定: {Fore.MAGENTA}{current_phase}{Style.RESET_ALL}")

    # 1. 加载昨收底库
    history_map = load_history_data()
    if not history_map: return
    
    # 1.5 加载策略池
    pool_map = load_strategy_pool()

    # 1.6 加载手动关注
    manual_focus = load_manual_focus()
    
    # 1.7 加载持仓
    holdings = load_holdings()
    
    valid_codes = set(pool_map.keys()) | set(holdings.keys())
    valid_names = set()
    
    for item in manual_focus:
        if item.isdigit(): valid_codes.add(item)
        else: valid_names.add(item)

    # 2. 获取实时数据
    live_df = get_live_data()
    if live_df.empty: return

    print(f"{Fore.CYAN}⚙️ [3/3] 正在进行策略计算 (基于周期: {current_phase})...{Style.RESET_ALL}")
    print(f"🎯 过滤范围: 持仓 {len(holdings)} + 策略 {len(pool_map)} + 手动 {len(manual_focus)}")

    results = []
    seen_codes = set()
    # 遍历实时数据进行匹配
    for _, row in live_df.iterrows():
        code = clean_code(row['code'])
        if code in seen_codes: continue
        seen_codes.add(code)
        name = str(row['name'])
        
        # --- 过滤逻辑 ---
        is_target = False
        if code in valid_codes: is_target = True
        if not is_target and name in valid_names: is_target = True
        
        if not is_target: continue
        # ----------------
        
        res = analyze_stock(row, history_map, pool_map, current_phase)
        if res:
            results.append(res)

    # Remove duplicates from results just in case
    unique_results = {}
    for r in results:
        unique_results[r['code']] = r
    results = list(unique_results.values())

    # 3. 排序与展示
    # 优先按分数降序，其次按竞价涨幅降序
    results.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print("\n" + "=" * 100)
    print(f"📊 实时监控报告 | 时间: {datetime.datetime.now().strftime('%H:%M:%S')} | 扫描: {len(live_df)} | 命中: {len(results)}")
    print(f"{'代码':<8} {'名称':<8} {'竞价%':<8} {'今/昨%':<12} {'连板':<6} {'市值':<8} {'竞/流%':<8} {'AI决策'}")
    print("-" * 110)

    count = 0
    for item in results:
        if item['score'] < 40: continue

        count += 1
        auc_str = f"{int(item['auc'] / 10000)}万"
        
        # 昨涨幅
        yest_pct = item.get('yest_pct', 0)
        c_yest = Fore.RED if yest_pct > 0 else Fore.GREEN
        pct_combo = f"{item['open_pct']:.1f}/{yest_pct:.1f}"
        
        # 连板
        boards = item.get('boards', 0)
        boards_str = str(boards) if boards > 0 else ""
        if boards >= 2: boards_str = f"{Fore.RED}{boards}板{Style.RESET_ALL}"
        
        # 市值
        mv_val = item.get('circ_mv', 0) / 100000000
        mv_str = f"{mv_val:.1f}亿"

        # 颜色处理
        c_open = Fore.RED if item['open_pct'] > 0 else Fore.GREEN
        
        # Tag display
        tag = item.get('tag', '')
        # 如果tag太长，截断一下？或者直接显示
        # 优化显示：将 Tag 附在 Decision 后，或者换行显示
        # User requested: "especially Fen Jue"
        # Let's append it to Decision column format
        
        decision_display = item['decision']
        if tag:
            # 清理一些不必要的符号如果需要
            decision_display += f" {Fore.YELLOW}{tag[:10]}{Style.RESET_ALL}" # 限制长度防止刷屏

        print(
            f"{item['code']:<8} "
            f"{item['name'][:4]:<8} "
            f"{c_open}{item['open_pct']:>5.2f}{Style.RESET_ALL}/"
            f"{c_yest}{yest_pct:<5.1f}{Style.RESET_ALL} "
            f"{boards_str:<6} "
            f"{mv_str:<8} "
            f"{item.get('r_mv', 0):<8.2f} " # J/L %
            f"{decision_display}"
            f" 额:{auc_str}"
        )

    if count == 0:
        print(f"{Fore.YELLOW}暂无符合【严格标准】的标的，请稍候再试...{Style.RESET_ALL}")

    print("=" * 100)


if __name__ == "__main__":
    # 检查当前时间，如果在9:25之前提醒用户
    now = datetime.datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute < 25):
        print(f"{Fore.YELLOW}⚠️ 提示：当前时间早于 9:25，Akshare 获取的成交额可能不是最终竞价金额。{Style.RESET_ALL}")

    main()