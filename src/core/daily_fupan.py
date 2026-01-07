# ==============================================================================
# 📌 F佬/Bo佬 智能盘后回测系统 (src/core/daily_fupan.py)
# v11.0 周期驱动版 - 已集成情绪周期引擎
# ==============================================================================
import pandas as pd
import os
import re
import sys
from colorama import init, Fore, Style, Back
from src.config import ProjectConfig
from src.core.emotion_cycle import EmotionalCycleEngine

# 解决 Windows 终端输出编码问题
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR))) # Adjust to root properly if needed, usually 2 up from src/core
# Fix root path calculation: src/core -> src -> project_root
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))

THS_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths', 'Table.txt')
POOL_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')

if not os.path.exists(THS_DATA_PATH): THS_DATA_PATH = "Table.txt"
if not os.path.exists(POOL_PATH): POOL_PATH = "strategy_pool.csv"


# ================= 🛠️ 工具函数 =================
def clean_unit(val):
    if pd.isna(val) or str(val).strip() in ['--', '']: return 0.0
    s = str(val).strip().replace(',', '').replace(' ', '')
    try:
        if '亿' in s: return float(s.replace('亿', '')) * 100000000
        if '万' in s: return float(s.replace('万', '')) * 10000
        if '%' in s: return float(s.replace('%', ''))
        return float(s)
    except:
        return 0.0


def clean_code(val):
    return re.sub(r'\D', '', str(val))


# ================= 🧠 核心策略逻辑 (周期驱动版) =================
def get_strategy_decision(item, cycle_phase):
    config = ProjectConfig()
    
    open_pct = item['open_pct']
    auc_amt = item.get('today_auction_amt', 0)
    circ_mv = item.get('circ_mv', 0)

    # 核心数据：昨日成交额
    yest_amt = item.get('yest_amt', 0)
    if yest_amt == 0:
        yest_amt = item.get('turnover', 0)  # 降级回退

    # 计算核心指标
    ratio_auc_to_yest = (auc_amt / yest_amt * 100) if yest_amt > 0 else 0
    ratio_auc_to_mv = (auc_amt / circ_mv * 100) if circ_mv > 0 else 0

    # 将指标存入 item 方便后续打印
    item['r_yest'] = ratio_auc_to_yest
    item['r_mv'] = ratio_auc_to_mv

    fail_reasons = []

    # --- 0. 基础清洗 ---
    if open_pct > 9.8: return f"{Fore.BLUE}一字板{Style.RESET_ALL}", 0
    if auc_amt < 300_0000: return "金额过小", 0  # 竞价金额小于300万直接过滤

    # --- 1. 竞价涨幅逻辑 (含弱转强) ---
    is_weak_to_strong = False

    if open_pct < -2.0:
        # 深水区：除非极度爆量做弱转强，否则剔除
        if ratio_auc_to_mv > config.WEAK_TO_STRONG_MV_RATIO:
            is_weak_to_strong = True
        else:
            return f"低开({open_pct}%)", 0
            
    elif open_pct < 1.8:
        # 平盘震荡区
        if ratio_auc_to_mv > config.WEAK_TO_STRONG_SHOCK_MV_RATIO:
            is_weak_to_strong = True
        else:
            fail_reasons.append(f"竞价弱({open_pct}%)")

    # --- 2. 竞价/昨日成交额 (动态调整) ---
    # 默认标准
    min_ratio = config.AUCTION_RATIO_MIN
    max_ratio = config.AUCTION_RATIO_MAX
    
    # 动态调整：如果是退潮期，要求更高承接
    if cycle_phase == config.PHASE_DECLINE:
        min_ratio = 5.0 # 提高门槛
        
    if ratio_auc_to_yest < min_ratio:
        fail_reasons.append(f"承接弱({ratio_auc_to_yest:.1f}%)")
    elif ratio_auc_to_yest > max_ratio:
        if not is_weak_to_strong:
            fail_reasons.append(f"过热({ratio_auc_to_yest:.1f}%)")

    # --- 3. 市值分层 & 竞价/市值比 ---
    mv_yi = circ_mv / 100000000.0
    mv_limit = 0.82
    if mv_yi < 20.0:
        mv_limit = 0.95  # 微盘要求更高
    elif 20.0 <= mv_yi < 27.0:
        mv_limit = 0.78  

    # 动态调整：如果是冰点期，对微盘股稍微宽容一点，博弈反核
    if cycle_phase == config.PHASE_ICE_POINT and mv_yi < 20.0:
        mv_limit = 0.8 # 降低要求

    if ratio_auc_to_mv < mv_limit:
        fail_reasons.append(f"量不足({ratio_auc_to_mv:.2f}% < {mv_limit}%)")

    # --- 综合判定 ---
    if len(fail_reasons) > 0:
        return f"{fail_reasons[0]}", 40

    # 成功入选
    score = 80
    decision = ""

    if is_weak_to_strong:
        decision = f"{Fore.MAGENTA}★ 弱转强{Style.RESET_ALL}"
        score = 85
    else:
        decision = f"{Fore.RED}★ 达标关注{Style.RESET_ALL}"

    # 完美模型加分
    perfect_min = config.AUCTION_RATIO_RECOMMEND_MIN
    perfect_max = config.AUCTION_RATIO_RECOMMEND_MAX
    
    if open_pct > 4.0 and perfect_min <= ratio_auc_to_yest <= perfect_max:
        score = 95
        decision = f"{Back.RED}{Fore.WHITE} 🔥 完美 {Style.RESET_ALL}"

    return decision, score


# ================= 📂 数据加载 =================
def get_latest_data_path():
    """
    智能查找最新的数据文件
    优先级: Table_YYYYMMDD.txt (按日期最新) > Table.txt
    """
    base_dir = os.path.dirname(THS_DATA_PATH)
    if not os.path.exists(base_dir): return THS_DATA_PATH # Fallback
    
    files = os.listdir(base_dir)
    candidates = []
    
    for f in files:
        # 匹配 Table_20240101.txt 或 Table.txt
        if f.startswith("Table") and f.endswith(".txt"):
            full_path = os.path.join(base_dir, f)
            # 尝试提取日期
            date_match = re.search(r'20\d{6}', f)
            date_int = int(date_match.group()) if date_match else 0
            
            # 如果是 Table.txt，给个基础权重，或者视为当天/未知
            if f == "Table.txt":
                # 获取文件修改时间作为参考，或者给个极大值/极小值
                # 这里假设 Table.txt 是最新的手动导出
                mtime = os.path.getmtime(full_path)
                candidates.append({'path': full_path, 'date': 99999999, 'mtime': mtime})
            else:
                candidates.append({'path': full_path, 'date': date_int, 'mtime': 0})
    
    if not candidates:
        return THS_DATA_PATH
        
    # 按日期(如果有)或文件名排序
    # 策略: 优先找文件名带日期的最新一个；如果没有带日期的，用 Table.txt
    
    dated_files = [c for c in candidates if c['date'] > 0 and c['date'] != 99999999]
    if dated_files:
        dated_files.sort(key=lambda x: x['date'], reverse=True)
        return dated_files[0]['path']
        
    # 如果只有 Table.txt 或其他不带日期的
    return THS_DATA_PATH

def load_data():
    target_path = get_latest_data_path()
    
    if not os.path.exists(target_path):
        print(f"{Fore.RED}❌ 错误: 未找到数据文件 (搜索路径: {os.path.dirname(THS_DATA_PATH)}){Style.RESET_ALL}")
        return []

    print(f"{Fore.CYAN}📂 正在读取: {os.path.basename(target_path)}{Style.RESET_ALL}")

    try:
        with open(target_path, 'r', encoding='gbk') as f:
            content = f.read()
    except:
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            return []

    lines = [line.strip() for line in content.split('\n') if line.strip()]

    # 智能查找表头
    header_idx = -1
    for i, line in enumerate(lines):
        if '代码' in line and '名称' in line:
            header_idx = i
            break
    if header_idx == -1: return []

    headers = re.split(r'\s+', lines[header_idx])
    col_map = {h: i for i, h in enumerate(headers)}

    # 列名映射 (兼容模糊匹配)
    def get_col(candidates):
        for c in candidates:
            if c in col_map: return col_map[c]
            for h in col_map:
                if c in h: return col_map[h]
        return -1

    idx_code = get_col(['代码'])
    idx_name = get_col(['名称'])
    idx_open = get_col(['竞价涨幅'])
    idx_auc = get_col(['早盘竞价金额', '竞价金额'])
    idx_pct = get_col(['涨幅', '涨跌幅'])
    idx_mv = get_col(['流通市值'])
    idx_price = get_col(['现价'])
    idx_yest = get_col(['昨日成交额', '昨成交'])
    idx_to = get_col(['当日成交额', '成交额'])

    data = []
    # 策略池过滤
    pool_set = set()
    if os.path.exists(POOL_PATH):
        try:
            pool_df = pd.read_csv(POOL_PATH, dtype=str)
            if 'code' in pool_df.columns:
                pool_set = set(pool_df['code'].apply(clean_code))
            elif 'sina_code' in pool_df.columns:
                pool_set = set(pool_df['sina_code'].apply(clean_code))
        except:
            pass

    is_pool_mode = len(pool_set) > 0
    if is_pool_mode:
        print(f"✅ 策略池模式: 锁定 {len(pool_set)} 只标的")

    for line in lines[header_idx + 1:]:
        row = re.split(r'\s+', line)
        if len(row) < len(headers): continue
        try:
            code = clean_code(row[idx_code])
            if is_pool_mode and code not in pool_set: continue

            item = {
                'code': code,
                'name': row[idx_name],
                'open_pct': clean_unit(row[idx_open]),
                'today_auction_amt': clean_unit(row[idx_auc]),
                'pct': clean_unit(row[idx_pct]),
                'turnover': clean_unit(row[idx_to]),
                'circ_mv': clean_unit(row[idx_mv]),
                'curr_p': clean_unit(row[idx_price]),
                'yest_amt': clean_unit(row[idx_yest]) if idx_yest != -1 else 0
            }

            if item['yest_amt'] == 0 and item['turnover'] > 0:
                item['yest_amt'] = item['turnover']
                item['data_source'] = '当日(模拟)'
            else:
                item['data_source'] = '昨日(精准)'

            if item['curr_p'] > 0: data.append(item)
        except:
            continue

    return data


# ================= 📈 主程序 =================
def run_backtest():
    # 1. 情绪分析
    try:
        engine = EmotionalCycleEngine()
        engine.fetch_market_mood(days=5) # 预热数据
        phase = engine.determine_phase()
        suggestion = engine.get_strategy_suggestion()
        
        print("\n" + "=" * 110)
        print(f"🌡️ 市场情绪周期: {Back.BLUE}{Fore.WHITE} {phase} {Style.RESET_ALL}")
        print(f"💡 策略建议: {Fore.YELLOW}{suggestion}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}⚠️ 情绪引擎初始化失败: {e}{Style.RESET_ALL}")
        phase = ProjectConfig.PHASE_DIVERGENCE # 默认降级为分歧

    # 2. 数据处理
    data = load_data()
    if not data: return

    results = []
    for item in data:
        decision, score = get_strategy_decision(item, phase)
        item['decision'] = decision
        item['score'] = score
        results.append(item)

    df = pd.DataFrame(results)
    df = df.sort_values(by=['score', 'open_pct'], ascending=[False, False])
    display_df = df[df['score'] >= 0]

    print("\n" + "=" * 110)
    print(f"📊 策略回测报告 (v11.0 周期驱动版) | 样本: {len(df)}")
    print(f"{'代码':<8} {'名称':<8} {'竞价%':<8} {'现涨%':<8} {'竞/昨%':<8} {'竞/流%':<8} {'决策结果'}")
    print("-" * 110)

    for _, row in display_df.iterrows():
        res_color = Fore.RED if row['pct'] > 0 else Fore.GREEN
        score_color = Style.BRIGHT if row['score'] >= 80 else ""

        # 竞价占比高亮
        r_yest_str = f"{row['r_yest']:.2f}"
        if 5.0 <= row['r_yest'] <= 15.0: r_yest_str = f"{Fore.YELLOW}{r_yest_str}{Style.RESET_ALL}"

        print(
            f"{score_color}{row['code']:<8} "
            f"{row['name'][:4]:<8} "
            f"{row['open_pct']:<8.2f} "
            f"{res_color}{row['pct']:<8.2f}{Style.RESET_ALL}{score_color} "
            f"{r_yest_str:<8} "
            f"{row['r_mv']:<8.2f} "
            f"{row['decision']}{Style.RESET_ALL}"
        )

    targets = df[df['score'] >= 80]
    if len(targets) > 0:
        wins = targets[targets['pct'] > 0]
        limit_ups = targets[targets['pct'] >= 9.8]
        avg_ret = targets['pct'].mean()

        print("-" * 110)
        print(f"🎯 入选标的: {len(targets)} 只")
        print(
            f"🏆 胜率 (>0%):   {Fore.RED}{len(wins) / len(targets) * 100:.1f}%{Style.RESET_ALL} (涨停: {len(limit_ups)})")
        print(f"📈 平均收益:      {Fore.RED if avg_ret > 0 else Fore.GREEN}{avg_ret:.2f}%{Style.RESET_ALL}")
    else:
        print("-" * 110)
        print(f"{Fore.YELLOW}⚠️ 无标的达标。建议检查数据源是否包含正确的'昨日成交额'列。{Style.RESET_ALL}")

    print("=" * 110)


if __name__ == "__main__":
    run_backtest()
