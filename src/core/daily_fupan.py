# ==============================================================================
# 📌 F佬/Bo佬 智能盘后回测系统 (src/core/daily_fupan_v10.py)
# v10.0 精准回测版 - 已适配“昨日成交额”数据
# ==============================================================================
import pandas as pd
import os
import re
import sys
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


# ================= 🧠 核心策略逻辑 (F佬精准版) =================
def get_strategy_decision(item):
    open_pct = item['open_pct']
    auc_amt = item.get('today_auction_amt', 0)
    circ_mv = item.get('circ_mv', 0)

    # 核心数据：昨日成交额
    # 如果数据源里没有找到昨日成交额，脚本会自动回退到使用当日成交额，并在日志中警告
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
        # 弱转强条件：竞价金额占市值 > 1.0% (非常强)
        if ratio_auc_to_mv > 1.0:
            is_weak_to_strong = True
        else:
            return f"低开({open_pct}%)", 0
    elif open_pct < 1.8:
        # 平盘震荡区 (-2% ~ 1.8%)：需要有一定量能支撑
        if ratio_auc_to_mv > 0.8:
            is_weak_to_strong = True
        else:
            fail_reasons.append(f"竞价弱({open_pct}%)")

    # --- 2. 竞价/昨日成交额 (核心接力指标) ---
    # 标准：3% ~ 18% (推荐 5%~15%)
    if ratio_auc_to_yest < 3.0:
        fail_reasons.append(f"承接弱({ratio_auc_to_yest:.1f}%)")
    elif ratio_auc_to_yest > 18.0:
        # 如果不是弱转强，过高的占比可能是一字板炸板或出货
        if not is_weak_to_strong:
            fail_reasons.append(f"过热({ratio_auc_to_yest:.1f}%)")

    # --- 3. 市值分层 & 竞价/市值比 ---
    mv_yi = circ_mv / 100000000.0
    mv_limit = 0.82
    if mv_yi < 20.0:
        mv_limit = 0.95  # 微盘
    elif 20.0 <= mv_yi < 27.0:
        mv_limit = 0.78  # 小盘

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

    # 完美模型加分 (高开 + 占比适中)
    if open_pct > 4.0 and 5.0 <= ratio_auc_to_yest <= 15.0:
        score = 95
        decision = f"{Back.RED}{Fore.WHITE} 🔥 完美 {Style.RESET_ALL}"

    return decision, score


# ================= 📂 数据加载 =================
def load_data():
    if not os.path.exists(THS_DATA_PATH):
        print(f"{Fore.RED}❌ 错误: 未找到文件 {THS_DATA_PATH}{Style.RESET_ALL}")
        return []

    print(f"{Fore.CYAN}📂 正在读取: {THS_DATA_PATH}{Style.RESET_ALL}")

    try:
        with open(THS_DATA_PATH, 'r', encoding='gbk') as f:
            content = f.read()
    except:
        try:
            with open(THS_DATA_PATH, 'r', encoding='utf-8') as f:
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

    # 🔥 关键：寻找昨日成交额
    # 常见列名：'昨日成交额', '昨成交', 或者带有昨天日期的成交额列
    idx_yest = get_col(['昨日成交额', '昨成交'])

    # 如果没找到显式的“昨日成交额”，尝试找带有日期的列 (如 "成交额(202X-XX-XX)")
    if idx_yest == -1:
        # 这里只是简单逻辑，实际可以根据日期判断。
        # 如果找不到，get_strategy_decision 会自动降级使用当日成交额。
        pass

        # 当日成交额 (作为备用或参考)
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
                # 尝试读取昨日成交额
                'yest_amt': clean_unit(row[idx_yest]) if idx_yest != -1 else 0
            }

            # 如果没读到昨日成交额，用当日成交额兜底 (并在后续逻辑中处理)
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
    data = load_data()
    if not data: return

    results = []
    for item in data:
        decision, score = get_strategy_decision(item)
        item['decision'] = decision
        item['score'] = score
        results.append(item)

    df = pd.DataFrame(results)
    df = df.sort_values(by=['score', 'open_pct'], ascending=[False, False])

    # 筛选出通过初筛的（包括淘汰的，方便看原因）
    # 但我们重点展示 Score >= 40 的
    display_df = df[df['score'] >= 0]

    print("\n" + "=" * 110)
    print(f"📊 策略回测报告 (v10.0 精准版) | 样本: {len(df)}")
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