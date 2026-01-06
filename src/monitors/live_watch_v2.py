# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src/core/live_watch_akshare.py)
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
# 静态底库：必须是【前一日收盘后】导出的数据，包含“成交额”（即昨成交）
HISTORY_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths', 'Table.txt')

if not os.path.exists(HISTORY_PATH): HISTORY_PATH = "Table.txt"


# ================= 🛠️ 工具函数 =================
def clean_unit(val):
    """清洗同花顺带单位的数值"""
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
    """统一为6位数字代码"""
    return re.sub(r'\D', '', str(val)).zfill(6)


# ================= 1. 加载历史底库 (昨成交) =================
def load_history_data():
    print(f"{Fore.CYAN}📂 [1/3] 正在加载静态底库 (昨收数据): {HISTORY_PATH}...{Style.RESET_ALL}")

    if not os.path.exists(HISTORY_PATH):
        print(f"{Fore.RED}❌ 错误: 未找到 Table.txt！请先导出今日收盘数据。{Style.RESET_ALL}")
        return {}

    try:
        # 尝试读取，兼容不同编码
        try:
            with open(HISTORY_PATH, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
                content = f.read()

        lines = [line.strip() for line in content.split('\n') if line.strip()]

        # 找表头
        header_idx = -1
        for i, line in enumerate(lines):
            if '代码' in line and '名称' in line:
                header_idx = i
                break
        if header_idx == -1: return {}

        headers = re.split(r'\s+', lines[header_idx])
        col_map = {h: i for i, h in enumerate(headers)}

        # 寻找关键列
        def get_idx(keys):
            for k in keys:
                if k in col_map: return col_map[k]
                for h in headers:
                    if k in h: return col_map[h]
            return -1

        idx_code = get_idx(['代码'])
        idx_mv = get_idx(['流通市值'])
        # 这里的“成交额”对明天来说就是“昨日成交额”
        idx_amt = get_idx(['成交额', '当日成交额'])

        history_map = {}
        for line in lines[header_idx + 1:]:
            row = re.split(r'\s+', line)
            if len(row) < len(headers): continue

            try:
                code = clean_code(row[idx_code])
                mv = clean_unit(row[idx_mv])
                amt = clean_unit(row[idx_amt])

                if amt > 0:
                    history_map[code] = {
                        'yest_amt': amt,  # 昨日成交额
                        'circ_mv': mv  # 流通市值
                    }
            except:
                continue

        print(f"✅ 底库加载完成，共 {len(history_map)} 只标的 (包含昨成交/市值)")
        return history_map

    except Exception as e:
        print(f"{Fore.RED}❌ 读取底库失败: {e}{Style.RESET_ALL}")
        return {}


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


# ================= 3. 策略判定 (核心) =================
def analyze_stock(row, history_info):
    """
    row: 实时数据 (Akshare)
    history_info: 静态数据 (Table.txt)
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

    if yest_amt == 0 or circ_mv == 0: return None

    # 3. 计算指标
    ratio_yest = (auc_amt / yest_amt * 100)
    ratio_mv = (auc_amt / circ_mv * 100)

    # 4. 策略逻辑 (F佬 v10.0 精准版)
    score = 60
    decision = "观察"
    fail_msg = ""
    is_qualified = False
    is_weak_to_strong = False  # 弱转强标记

    # --- 规则0: 基础过滤 ---
    if auc_amt < 300_0000: return None  # 竞价小于300万直接忽略
    if open_pct > 9.8: return {'code': code, 'name': name, 'score': 0,
                               'decision': f"{Fore.BLUE}一字板{Style.RESET_ALL}", 'open_pct': open_pct, 'auc': auc_amt}

    # --- 规则1: 竞价涨幅 (含弱转强) ---
    if open_pct < -2.0:
        # 深水区：必须超强爆量才算弱转强 (占比>1.0%市值)
        if ratio_mv > 1.0:
            is_weak_to_strong = True
        else:
            fail_msg = f"低开({open_pct}%)"
    elif open_pct < 1.8:
        # 平盘震荡区：需要一定承接 (占比>0.8%市值)
        if ratio_mv > 0.8:
            is_weak_to_strong = True
        else:
            fail_msg = f"竞价弱({open_pct}%)"

    # --- 规则2: 竞价/昨成交 (3% - 18%) ---
    # 如果是弱转强，对这个条件可以适当放宽，或者作为加分项
    if ratio_yest < 3.0:
        # 如果不是弱转强，则必须满足3%
        if not is_weak_to_strong:
            fail_msg = f"承接弱({ratio_yest:.1f}%)"
    elif ratio_yest > 18.0:
        if not is_weak_to_strong:
            fail_msg = f"过热({ratio_yest:.1f}%)"

    # --- 规则3: 市值分层 ---
    mv_yi = circ_mv / 100000000.0
    limit = 0.82
    if mv_yi < 20.0:
        limit = 0.95
    elif 20.0 <= mv_yi < 27.0:
        limit = 0.78

    if ratio_mv < limit:
        # 弱转强如果不满足市值比，也得淘汰
        fail_msg = f"量不足({ratio_mv:.2f}% < {limit}%)"

    # --- 结论 ---
    if fail_msg:
        # 即使失败，如果是弱转强且量能很大，也保留观察
        return {'code': code, 'name': name, 'score': 40, 'decision': fail_msg, 'open_pct': open_pct, 'auc': auc_amt,
                'r_yest': ratio_yest, 'r_mv': ratio_mv}

    # 成功入选
    if is_weak_to_strong:
        decision = f"{Fore.MAGENTA}★ 弱转强{Style.RESET_ALL}"
        score = 85
    else:
        decision = f"{Fore.RED}★ 达标关注{Style.RESET_ALL}"
        score = 80

    # 完美模型
    if open_pct > 4.0 and 5.0 <= ratio_yest <= 15.0:
        decision = f"{Back.RED}{Fore.WHITE} 🔥 完美 {Style.RESET_ALL}"
        score = 95

    return {
        'code': code,
        'name': name,
        'score': score,
        'decision': decision,
        'open_pct': open_pct,
        'auc': auc_amt,
        'r_yest': ratio_yest,
        'r_mv': ratio_mv
    }


# ================= 🚀 主程序 =================
def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (Akshare版) {Style.RESET_ALL}")
    print("=" * 100)

    # 1. 加载昨收底库
    history_map = load_history_data()
    if not history_map: return

    # 2. 获取实时数据
    live_df = get_live_data()
    if live_df.empty: return

    print(f"{Fore.CYAN}⚙️ [3/3] 正在进行策略计算...{Style.RESET_ALL}")

    results = []
    # 遍历实时数据进行匹配
    for _, row in live_df.iterrows():
        res = analyze_stock(row, history_map)
        if res:
            results.append(res)

    # 3. 排序与展示
    # 优先按分数降序，其次按竞价涨幅降序
    results.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print("\n" + "=" * 100)
    print(
        f"📊 实时监控报告 | 时间: {datetime.datetime.now().strftime('%H:%M:%S')} | 扫描: {len(live_df)} | 命中: {len(results)}")
    print(f"{'代码':<8} {'名称':<8} {'竞价%':<8} {'竞价额':<10} {'竞/昨%':<8} {'竞/流%':<8} {'AI决策'}")
    print("-" * 100)

    count = 0
    for item in results:
        # 只显示分数 >= 40 的（过滤掉完全没戏的，或者你可以改成 >= 70 只看达标的）
        if item['score'] < 70: continue

        count += 1
        auc_str = f"{int(item['auc'] / 10000)}万"

        # 颜色处理
        c_open = Fore.RED if item['open_pct'] > 0 else Fore.GREEN

        # 竞价占比高亮
        r_yest_val = item.get('r_yest', 0)
        r_yest_str = f"{r_yest_val:.1f}"
        if 5.0 <= r_yest_val <= 15.0: r_yest_str = f"{Fore.YELLOW}{r_yest_str}{Style.RESET_ALL}"

        print(
            f"{item['code']:<8} "
            f"{item['name'][:4]:<8} "
            f"{c_open}{item['open_pct']:<8.2f}{Style.RESET_ALL} "
            f"{auc_str:<10} "
            f"{r_yest_str:<8} "
            f"{item.get('r_mv', 0):<8.2f} "
            f"{item['decision']}"
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