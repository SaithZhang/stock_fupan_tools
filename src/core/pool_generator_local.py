# ==============================================================================
# 📌 1-L. F佬/Bo佬 离线复盘生成器 (Local Smart Version) - v1.6 智能表头版
# 功能：自动识别带日期的同花顺表头，抓取最新数据，严格复刻API逻辑
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
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= 1. 路径与配置 =================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# 输入文件
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')
LOCAL_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_all_data.txt')

# 输出文件
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

# --- 策略参数 ---
CORE_KEYWORDS = [
    '机器人', '航天', '军工', '卫星', '低空',
    'AI', '人工智能', '智能体', '算力', 'CPO', '存储',
    '消费电子', '华为', '信创', '数字货币', '数据要素',
    '文化传媒', '短剧', '多模态', '纺织', '并购重组', '固态电池', '自动驾驶'
]

HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('AI智能体', 'concept'),
    ('消费电子', 'industry'),
    ('低空经济', 'concept'),
    ('数字货币', 'concept'),
    ('文化传媒', 'industry'),
]

HOLDING_STRATEGIES = {
    '603667': ('持仓/五洲(机器人/航天)', ''),
    '300115': ('持仓/长盈(消电中军)', 'sz002475'),
    '001231': ('持仓/农心(农业)', ''),
}

LINK_DRAGON_MAP = {
    '002009': '002931',
}

# 全局数据缓存
ALL_LOCAL_DATA = {}


# ================= 2. 智能解析核心 =================

def parse_val(v):
    """数值清洗工具"""
    if not v or '--' in str(v): return 0.0
    v = str(v).replace(',', '')
    if '亿' in v: v = v.replace('亿', '*100000000')
    if '万' in v: v = v.replace('万', '*10000')
    if '%' in v: v = v.replace('%', '*0.01')
    try:
        return float(eval(v))
    except:
        return 0.0


def resolve_best_column(headers, keywords):
    """
    在表头中查找包含关键词的列。
    如果有多列命中（如'成交额[2025]'和'成交额[2026]'），取日期最新的那一列。
    返回: 最佳列的索引 (int) 或 -1 (未找到)
    """
    candidates = []
    for idx, h in enumerate(headers):
        for kw in keywords:
            if kw in h:
                # 尝试提取日期
                date_match = re.search(r'(\d{8})', h)
                date_val = int(date_match.group(1)) if date_match else 99999999  # 无日期视为永久/最新
                candidates.append((idx, h, date_val))
                break

    if not candidates:
        return -1

    # 按日期降序排列，取第一个
    candidates.sort(key=lambda x: x[2], reverse=True)
    best = candidates[0]
    # print(f"   ℹ️ 列匹配: '{keywords[0]}' -> 使用 '{best[1]}'") # 调试用
    return best[0]


def load_local_ths_data():
    global ALL_LOCAL_DATA
    if not os.path.exists(LOCAL_DATA_PATH):
        print(f"{Fore.RED}❌ 未找到文件: {LOCAL_DATA_PATH}")
        return False

    print(f"{Fore.MAGENTA}📂 正在解析本地数据 (Smart Mode v1.6)...{Fore.RESET}")
    lines = []
    for enc in ['utf-8', 'gbk', 'gb18030', 'utf-16']:
        try:
            with open(LOCAL_DATA_PATH, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except:
            continue

    lines = [L for L in lines if L.strip()]
    if not lines:
        print(f"{Fore.RED}❌ 文件为空或无法读取{Fore.RESET}")
        return False

    if len(lines) < 100:
        print(f"{Fore.YELLOW}⚠️ 警告: 数据行数仅 {len(lines)} 行，请确认是否导出了【所有数据】！{Fore.RESET}")

    headers = re.split(r'\t+|\s{2,}', lines[0].strip())

    # --- 智能映射表头 ---
    col_map = {}

    # 基础列
    col_map['code'] = resolve_best_column(headers, ['代码'])
    col_map['name'] = resolve_best_column(headers, ['名称'])
    col_map['price'] = resolve_best_column(headers, ['现价'])
    col_map['pct'] = resolve_best_column(headers, ['涨幅'])
    col_map['turnover'] = resolve_best_column(headers, ['换手'])
    col_map['pct_10'] = resolve_best_column(headers, ['10日涨幅'])
    col_map['prev_close'] = resolve_best_column(headers, ['昨收'])
    col_map['open'] = resolve_best_column(headers, ['今开'])
    col_map['high'] = resolve_best_column(headers, ['最高'])

    # 关键动态列 (带日期)
    col_map['amount'] = resolve_best_column(headers, ['成交额'])
    col_map['vol'] = resolve_best_column(headers, ['成交量', '总手'])
    col_map['limit_days'] = resolve_best_column(headers, ['连板', '连续涨停'])
    col_map['open_num'] = resolve_best_column(headers, ['开板', '炸板'])
    col_map['concepts'] = resolve_best_column(headers, ['概念', '行业', '涨停原因'])

    # 检查缺失
    missing = [k for k, v in col_map.items() if v == -1 and k in ['limit_days', 'amount', 'open_num']]
    if missing:
        print(f"{Fore.RED}❌ 依然缺少关键列: {missing}。请检查表头设置！{Fore.RESET}")
        # 这里不return，尝试硬跑

    count = 0
    for line in lines[1:]:
        parts = re.split(r'\t+|\s{2,}', line.strip())
        if len(parts) < 5: continue

        # 安全取值 helper
        def get_val(key, default=0):
            idx = col_map.get(key, -1)
            if idx != -1 and idx < len(parts): return parts[idx]
            return default

        raw_code = get_val('code', '000000')
        code = re.sub(r'\D', '', raw_code)
        if len(code) != 6: continue

        try:
            price = parse_val(get_val('price'))
            pct = parse_val(get_val('pct'))
            if abs(pct) < 0.3 and pct != 0: pct *= 100

            # 关键逻辑字段
            limit_days_str = get_val('limit_days', '0')
            limit_days = int(parse_val(limit_days_str))

            open_num_str = get_val('open_num', '0')
            open_num = int(parse_val(open_num_str))

            amount = parse_val(get_val('amount'))

            # 概念可能是字符串
            concept_str = str(get_val('concepts', ''))

            # 兜底：如果没找到连板列，尝试通过涨幅推断首板
            high = parse_val(get_val('high'))
            is_zt_approx = (pct > 9.8) and (high == price)

            data = {
                'code': code,
                'name': str(get_val('name', '未知')),
                'price': price,
                'today_pct': pct,
                'amount': amount,
                'vol': parse_val(get_val('vol')),
                'turnover': parse_val(get_val('turnover')),
                'pct_10': parse_val(get_val('pct_10')),
                'limit_days': limit_days,
                'open_num': open_num,
                'concept_str': concept_str,
                'is_zt_approx': is_zt_approx,
                'prev_close': parse_val(get_val('prev_close')),
                'open_price': parse_val(get_val('open')),
                'vol_ratio': 1.0,
                'vol_prev': 0.0
            }

            # 补齐计算
            if data['prev_close'] == 0: data['prev_close'] = price
            if data['open_price'] == 0: data['open_price'] = price

            if data['prev_close'] > 0:
                data['open_pct'] = round((data['open_price'] - data['prev_close']) / data['prev_close'] * 100, 2)

            # 简单的昨量估算 (因为本地可能缺昨量列)
            data['vol_prev'] = data['vol']  # 暂且相等

            ALL_LOCAL_DATA[code] = data
            count += 1
        except Exception as e:
            continue

    print(f"   ↳ 成功加载 {count} 条数据")
    return count > 0


# ================= 3. 通用辅助函数 (保持不变) =================

def format_sina(code):
    if code.startswith('6'): return f"sh{code}"
    if code.startswith('8') or code.startswith('4'): return f"bj{code}"
    return f"sz{code}"


def get_link_dragon(code):
    if code in HOLDING_STRATEGIES:
        dragon = HOLDING_STRATEGIES[code][1]
        if dragon: return dragon
    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon: return dragon if dragon.startswith('s') else format_sina(dragon)
    return ''


def get_core_concepts(code, name):
    if code not in ALL_LOCAL_DATA: return ""
    raw = ALL_LOCAL_DATA[code]['concept_str']
    matched = set()
    for key in CORE_KEYWORDS:
        if key in raw: matched.add(key)
    return "/".join(list(matched))


def get_market_data(code):
    if code in ALL_LOCAL_DATA:
        d = ALL_LOCAL_DATA[code]
        return {
            'vol': d['vol'], 'amount': d['amount'], 'vol_prev': d['vol_prev'],
            'vol_ratio': d['vol_ratio'], 'pct_10': d['pct_10'], 'price': d['price'],
            'open_pct': d['open_pct'], 'today_pct': d['today_pct'], 'turnover': d['turnover'],
            'low': d['price'] * 0.9, 'high': d['price'] * 1.1, 'prev_close': d['prev_close']
        }
    return None


def check_special_shape(m_data):
    tags = []
    if m_data:
        if m_data['today_pct'] > 9.0 and m_data['open_pct'] < -5.0: tags.append("🔥长腿/疑似地天")
        if m_data['today_pct'] > 14.0: tags.append("🔥20cm")
        amt_yi = m_data['amount'] / 100000000
        if amt_yi > 20.0:
            tags.append("💰大战场")
        elif amt_yi < 0.5:
            tags.append("⚠️流动性差")
    return tags


def load_manual_lists():
    combined = {}
    if os.path.exists(THS_PATH):
        try:
            with open(THS_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except:
            try:
                with open(THS_PATH, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            except:
                lines = []
        for line in lines:
            line = line.strip()
            if not line or "代码" in line: continue
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                code = parts[0].replace("SZ", "").replace("SH", "")
                if code.isdigit(): combined[code] = f"同花顺/{parts[1]}"

    if os.path.exists(HOLDINGS_PATH):
        try:
            with open(HOLDINGS_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if "代码" in line: continue
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) >= 2: combined[parts[0]] = f"持仓/{parts[1]}"
        except:
            pass

    if os.path.exists(F_LAO_PATH):
        try:
            with open(F_LAO_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip() or line.startswith('#'): continue
                    parts = re.split(r'\s+', line.strip(), maxsplit=1)
                    if len(parts) >= 2: combined[parts[0]] = parts[1]
        except:
            pass
    return combined


# ================= 4. 主逻辑 =================

def generate_csv():
    if not load_local_ths_data(): return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    strategy_rows = []
    seen_codes = set()

    def add_item(code, name, base_tag):
        if code in seen_codes or code not in ALL_LOCAL_DATA: return
        m_data = get_market_data(code)
        extra = get_core_concepts(code, name)
        specials = check_special_shape(m_data)
        tag_list = [base_tag]
        if extra: tag_list.append(extra)
        tag_list.extend(specials)
        final_tag = "/".join(tag_list)

        strategy_rows.append({
            'code': code, 'name': name, 'tag': final_tag,
            'link_dragon': get_link_dragon(code),
            'vol': int(m_data['vol']), 'amount': m_data['amount'],
            'vol_prev': int(m_data['vol_prev']), 'vol_ratio': m_data.get('vol_ratio', 0),
            'pct_10': m_data['pct_10'], 'price': m_data['price'],
            'open_pct': m_data['open_pct'], 'today_pct': m_data['today_pct'],
            'turnover': m_data['turnover']
        })
        seen_codes.add(code)
        print(f"入池: {name:<8} ({final_tag})")

    # [1] 涨停
    print(f"\n{Fore.YELLOW}[1/5] 筛选涨停...{Fore.RESET}")
    for code, d in ALL_LOCAL_DATA.items():
        if d['limit_days'] > 0:
            tag = f"{d['limit_days']}板"
            if d['open_num'] > 0:
                tag += f"/回封(炸{d['open_num']})"
            else:
                tag += "/硬板"
            add_item(code, d['name'], tag)
        elif d['is_zt_approx']:
            add_item(code, d['name'], "1板/首板")

    # [2] 炸板
    print(f"\n{Fore.YELLOW}[2/5] 筛选炸板...{Fore.RESET}")
    for code, d in ALL_LOCAL_DATA.items():
        if d['open_num'] > 0 and d['limit_days'] == 0 and d['today_pct'] > -8.0:
            add_item(code, d['name'], "炸板/反包预期")

    # [3] 跌停
    print(f"\n{Fore.YELLOW}[3/5] 筛选跌停...{Fore.RESET}")
    for code, d in ALL_LOCAL_DATA.items():
        if d['today_pct'] < -9.8:
            add_item(code, d['name'], "跌停/博弈修复")

    # [4] 中军
    print(f"\n{Fore.YELLOW}[4/5] 筛选板块中军...{Fore.RESET}")
    for concept_kw, _ in HOT_CONCEPTS:
        candidates = [d for code, d in ALL_LOCAL_DATA.items() if concept_kw in d['concept_str']]
        candidates.sort(key=lambda x: x['amount'], reverse=True)
        for d in candidates[:2]:
            tag_s = f"{concept_kw}中军"
            if d['code'] in seen_codes:
                # 更新已有
                for row in strategy_rows:
                    if row['code'] == d['code'] and tag_s not in row['tag']:
                        row['tag'] += f"/{tag_s}"
            else:
                add_item(d['code'], d['name'], tag_s)

    # [5] 关注列表
    print(f"\n{Fore.YELLOW}[5/5] 注入关注列表...{Fore.RESET}")
    manual = load_manual_lists()
    for code, tag in manual.items():
        if code in ALL_LOCAL_DATA:
            if code in seen_codes:
                for row in strategy_rows:
                    if row['code'] == code:
                        clean = tag.split('/')[1] if '/' in tag else tag
                        if clean not in row['tag']: row['tag'] = f"{clean}/{row['tag']}"
            else:
                add_item(code, ALL_LOCAL_DATA[code]['name'], tag)

    # 导出
    if strategy_rows:
        df = pd.DataFrame(strategy_rows)
        df['sina_code'] = df['code'].apply(format_sina)
        df.sort_values(by='amount', ascending=False, inplace=True)
        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10',
                'link_dragon', 'vol', 'vol_prev', 'code']
        df = df.reindex(columns=cols)

        date_str = datetime.now().strftime("%Y%m%d")
        save_path = os.path.join(ARCHIVE_DIR, f'strategy_pool_LOCAL_{date_str}.csv')
        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        shutil.copyfile(save_path, os.path.join(OUTPUT_DIR, 'strategy_pool.csv'))
        print(f"\n{Fore.GREEN}✅ 成功生成 {len(df)} 只标的！{Fore.RESET}")
    else:
        print(f"{Fore.RED}❌ 结果为空。请检查数据源是否包含涨停股。{Fore.RESET}")


if __name__ == "__main__":
    generate_csv()