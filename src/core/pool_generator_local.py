# ==============================================================================
# 📌 1-H. F佬/Bo佬 离线复盘生成器 (鲁棒防崩版)
# 修复: IndexError: list index out of range (针对行尾缺失列的自动补全)
# ==============================================================================

import pandas as pd
import os
import sys
import re
import shutil
from datetime import datetime
from colorama import init, Fore

# 适配 Windows 控制台
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# 输入文件: 你的同花顺全量数据
INPUT_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_all_data.txt')

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')
LATEST_PATH = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')


# ================= 🛠️ 核心工具函数 =================

def format_sina(code):
    """标准化代码格式 sz000001"""
    code = str(code).strip().lower()
    if code.isdigit():
        if code.startswith('6'): return f"sh{code}"
        if code.startswith('8') or code.startswith('4'): return f"bj{code}"
        return f"sz{code}"
    # 处理 SZ300500 这种带前缀的
    return code.replace('sz', 'sz').replace('sh', 'sh').lower()


def safe_get(lst, idx, default="0"):
    """👉 核心修复：安全获取列表元素，防越界"""
    if 0 <= idx < len(lst):
        return lst[idx]
    return default


def parse_val(v):
    """数值清洗：处理 '1.2亿', '--', '15%' 等"""
    if not v or '--' in v: return 0.0
    # 移除千分位逗号，处理单位
    v = v.replace(',', '')
    v = v.replace('亿', '*100000000').replace('万', '*10000').replace('%', '*0.01').replace('+', '')
    try:
        return float(eval(v))
    except:
        return 0.0


def parse_robust_data():
    if not os.path.exists(INPUT_PATH):
        print(f"{Fore.RED}❌ 未找到文件: {INPUT_PATH}")
        print(f"{Fore.YELLOW}👉 请将同花顺导出数据保存为 'ths_all_data.txt' 放入 data/input/ 目录{Fore.RESET}")
        return None

    print(f"{Fore.CYAN}💎 正在解析同花顺全量数据 (鲁棒模式)...{Fore.RESET}")

    lines = []
    # 尝试多种编码读取
    encodings = ['utf-8', 'gbk', 'gb18030', 'utf-16']
    for enc in encodings:
        try:
            with open(INPUT_PATH, 'r', encoding=enc) as f:
                lines = f.readlines()
            print(f"   ↳ 成功使用 {enc} 编码读取")
            break
        except UnicodeDecodeError:
            continue

    if not lines:
        print(f"{Fore.RED}❌ 读取失败：无法识别文件编码{Fore.RESET}")
        return None

    # --- 1. 智能表头解析 ---
    # 过滤空行
    lines = [L for L in lines if L.strip()]
    header_line = lines[0].strip()

    # 支持 制表符 或 多个空格 分隔
    headers = re.split(r'\t+|\s{2,}', header_line)

    col_map = {}
    print(f"   ↳ 识别到 {len(headers)} 列表头")

    for idx, h in enumerate(headers):
        h = h.strip()
        if '代码' in h:
            col_map['code'] = idx
        elif '名称' in h:
            col_map['name'] = idx
        elif '现价' in h:
            col_map['price'] = idx
        elif '涨幅' in h and '竞价' not in h:
            col_map['pct'] = idx
        elif '换手' in h:
            col_map['turnover'] = idx
        elif '竞价金额' in h:
            col_map['today_auction'] = idx

        # 自动识别成交额日期
        elif '成交额' in h:
            date_match = re.search(r'\[(\d+)\]', h)
            if date_match:
                date_val = int(date_match.group(1))
                if 'amt_cols' not in col_map: col_map['amt_cols'] = []
                col_map['amt_cols'].append((idx, date_val))

        elif '涨停开板次数' in h:
            col_map['open_num'] = idx
        elif '连续涨停天数' in h:
            col_map['limit_days'] = idx
        elif '涨停原因' in h:
            col_map['reason'] = idx

    # --- 2. 自动判定昨天和今天 ---
    yest_amt_idx = -1
    today_amt_idx = -1

    if 'amt_cols' in col_map and len(col_map['amt_cols']) > 0:
        sorted_amts = sorted(col_map['amt_cols'], key=lambda x: x[1], reverse=True)
        today_amt_idx = sorted_amts[0][0]
        if len(sorted_amts) >= 2:
            yest_amt_idx = sorted_amts[1][0]

    # --- 3. 解析数据行 ---
    strategy_rows = []

    for line in lines[1:]:
        # 智能切割
        parts = re.split(r'\t+|\s{2,}', line.strip())

        # 提取代码 (如果没有代码列，跳过)
        if 'code' not in col_map: continue
        raw_code = safe_get(parts, col_map['code'])
        # 简单校验代码长度，太短的可能是坏行
        if len(raw_code) < 6: continue

        code_num = re.sub(r'\D', '', raw_code)
        name = safe_get(parts, col_map.get('name', -1), "未知")

        # 基础数据
        price = parse_val(safe_get(parts, col_map.get('price', -1)))
        pct = parse_val(safe_get(parts, col_map.get('pct', -1))) * 100
        turnover = parse_val(safe_get(parts, col_map.get('turnover', -1))) * 100

        # 资金数据
        yest_amt = parse_val(safe_get(parts, yest_amt_idx))
        today_amt = parse_val(safe_get(parts, today_amt_idx))
        auction_amt = parse_val(safe_get(parts, col_map.get('today_auction', -1)))

        # 连板/炸板数据 (👉 这里是你之前报错的地方，现在安全了)
        open_num = int(parse_val(safe_get(parts, col_map.get('open_num', -1))))
        limit_days = int(parse_val(safe_get(parts, col_map.get('limit_days', -1))))
        reason = safe_get(parts, col_map.get('reason', -1), "")

        # --- 4. 构建标签 ---
        tags = ["导入"]

        # 连板标签
        if limit_days > 0:
            tags.append(f"{limit_days}板")

        # 气质标签
        if open_num > 0:
            tags.append(f"炸{open_num}次")
        elif limit_days > 0:
            tags.append("硬板")

        # 跌停反核标记 (结合你的反核策略，标记深水票)
        if pct < -9.0:
            tags.append("跌停/反核")

        # 概念提取
        if reason and reason != '无' and reason != '--':
            keywords = reason.split('+')[:2]
            tags.extend(keywords)

        # --- 5. 组装 ---
        row_data = {
            'code': code_num,
            'sina_code': format_sina(raw_code),
            'name': name,
            'tag': "/".join(tags),
            'amount': today_amt,
            'today_auction_amt': auction_amt,
            'history': {
                'yest_amt': yest_amt,
                'prev_amt': 0
            },
            'today_pct': pct,
            'price': price,
            'turnover': turnover,
            'open_pct': 0
        }

        strategy_rows.append(row_data)

    print(f"{Fore.GREEN}✅ 解析成功: {len(strategy_rows)} 只标的{Fore.RESET}")
    return pd.DataFrame(strategy_rows)


def save_csv(df):
    if df is None or df.empty: return

    df.sort_values(by='amount', ascending=False, inplace=True)

    cols = ['sina_code', 'name', 'tag', 'amount', 'today_auction_amt', 'today_pct', 'turnover', 'open_pct', 'price',
            'history', 'code']
    df = df.reindex(columns=cols)

    date_str = datetime.now().strftime("%Y%m%d")
    save_path = os.path.join(ARCHIVE_DIR, f'strategy_pool_ROBUST_{date_str}.csv')
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    df.to_csv(save_path, index=False, encoding='utf-8-sig')

    shutil.copyfile(save_path, LATEST_PATH)
    print(f"🔗 监控文件已更新: {LATEST_PATH}")
    print(f"🚀 就绪！可运行 python realtime_watch.py")


if __name__ == "__main__":
    df = parse_robust_data()
    save_csv(df)