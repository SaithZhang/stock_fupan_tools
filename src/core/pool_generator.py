import pandas as pd
import os
import shutil
import sys
import re
from datetime import datetime
from colorama import init, Fore

# --- 导入修复 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from .data_loader import get_merged_data
except ImportError:
    from data_loader import get_merged_data
# --------------

init(autoreset=True)

# ================= 1. 路径与配置 =================

PROJECT_ROOT = os.path.dirname(os.path.dirname(current_dir))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')

# --- 策略配置 (与 akshare 版保持一致) ---
CORE_KEYWORDS = [
    '机器人', '航天', '军工', '卫星', '低空',
    'AI', '人工智能', '智能体', '算力', 'CPO', '存储',
    '消费电子', '华为', '信创', '数字货币', '数据要素',
    '文化传媒', '短剧', '多模态', '纺织', '并购重组', '固态电池', '自动驾驶'
]

# 持仓股特殊策略配置 (代码: (标签, 联动大哥代码))
HOLDING_STRATEGIES = {
    '603667': ('持仓/五洲(机器人/航天)', ''),
    '300115': ('持仓/长盈(消电中军)', 'sz002475'),
    '001231': ('持仓/农心(农业)', ''),
}

# 联动大哥映射 (小弟代码: 大哥代码)
LINK_DRAGON_MAP = {
    '002009': '002931',
}


# ================= 2. 辅助函数 =================

def load_text_list(filepath):
    """加载关注列表/持仓列表"""
    if not os.path.exists(filepath): return {}
    mapping = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = re.split(r'\s+', line, maxsplit=1)
                code = parts[0].strip()
                # 简单清洗代码
                code = code.replace("SZ", "").replace("SH", "")
                if code.isdigit() and len(code) == 6:
                    tag = parts[1].strip() if len(parts) > 1 else "关注"
                    mapping[code] = tag
    except Exception as e:
        print(f"{Fore.RED}加载列表失败 {filepath}: {e}")
    return mapping


def format_sina(code):
    code = str(code)
    if code.startswith('6'): return f"sh{code}"
    if code.startswith('8') or code.startswith('4'): return f"bj{code}"
    return f"sz{code}"


def get_link_dragon(code):
    """获取关联的大哥代码"""
    if code in HOLDING_STRATEGIES:
        dragon = HOLDING_STRATEGIES[code][1]
        if dragon: return dragon

    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon:
        if dragon.startswith('sz') or dragon.startswith('sh'): return dragon
        return format_sina(dragon)
    return ''


def clean_manual_tag(tag, is_zt_tag_present):
    """
    清洗手动标签，避免冗余
    1. 去除重复的 'F佬' 前缀
    2. 如果有实时涨停数据，尝试移除手动备注中过时的 '3板' 等字样
    """
    if not tag: return ""

    # 1. 清理重复前缀 (如 "F佬/F佬/...")
    if tag.startswith("F佬/"):
        tag = tag[3:]
    elif tag.startswith("F佬"):
        tag = tag.lstrip("F佬").lstrip("/")

    # 2. 清理过时连板信息 (e.g. 备注是3板，但今天实际上4板了)
    if is_zt_tag_present:
        # 正则替换：匹配 "3板", "2连板" 等，且前后有分隔符或边界
        # 兼容 "雷科(3板/军工)" 这种括号内的写法
        tag = re.sub(r'(^|/|[(])\d+板([)]|/|$)', r'\1\2', tag)

        # 清理正则替换后留下的残留符号 (如 "//", "()")
        tag = tag.replace('()', '').replace('//', '/').replace('(/', '(').replace('/)', ')')
        tag = tag.strip('/')

    return tag


def get_unique_concepts(base_str, new_concepts_str):
    """
    仅返回 base_str (手动备注) 中不存在的新概念
    避免出现 "雷科(军工)/.../军工" 这种重复
    """
    if not new_concepts_str: return ""

    # 将 base_str 拆解为关键词集合 (按 / 和 括号 拆分)
    base_parts = re.split(r'[/()]', base_str)
    base_set = set(p.strip() for p in base_parts if p.strip())

    new_parts = new_concepts_str.split('/')
    final_new = []
    for c in new_parts:
        c = c.strip()
        # 如果新概念不在已有集合中，且不是已有字符串的子串 (防止 "军工" vs "军工板块" 重复)
        if c and c not in base_set and c not in base_str:
            final_new.append(c)

    return "/".join(final_new)


def get_core_concepts_local(name, raw_tag):
    """本地提取核心概念"""
    matched = set()
    source_text = f"{name} {raw_tag}"

    for key in CORE_KEYWORDS:
        if key in source_text:
            matched.add(key)

    return "/".join(list(matched))


def check_special_shape(item):
    """检查特殊形态 (地天板/20cm/资金面)"""
    tags = []
    pct = item.get('today_pct', 0)
    low_pct = 0
    if 'low' in item and 'prev_close' in item and item['prev_close'] > 0:
        low_pct = (item['low'] - item['prev_close']) / item['prev_close'] * 100

    if low_pct < -9.0 and pct > 9.0: tags.append("🔥地天板")
    if pct > 14.0: tags.append("🔥20cm")

    amount_val = item.get('amount', 0)
    amt_yi = amount_val / 100000000.0

    if amt_yi > 20.0:
        tags.append("💰大战场")
    elif amt_yi < 0.5 and amt_yi > 0:
        tags.append("⚠️流动性差")

    return tags


# ================= 3. 主生成逻辑 =================

def generate_strategy_pool():
    all_data = get_merged_data()
    if not all_data:
        print(f"{Fore.RED}❌ 数据源为空，请检查 data_loader")
        return

    holdings_map = load_text_list(HOLDINGS_PATH)
    f_lao_map = load_text_list(F_LAO_PATH)

    manual_focus = f_lao_map.copy()
    manual_focus.update(holdings_map)

    print(f"{Fore.CYAN}📋 离线生成启动 | 数据源: {len(all_data)}条 | 持仓: {len(holdings_map)} | 关注: {len(f_lao_map)}")

    pool = []

    for item in all_data:
        code = str(item['code'])
        name = item['name']
        pct = item.get('today_pct', 0)

        raw_tag_str = str(item.get('tag', ''))
        if 'nan' in raw_tag_str: raw_tag_str = ""

        base_tags = []
        is_selected = False
        has_zt_status = False  # 是否有涨停状态

        # --- 1. 涨停状态预判 ---
        # 先判断涨停，方便后续清洗手动标签时知道是否要移除旧板数
        is_zt = item.get('is_zt') or (pct >= 9.8)
        zt_tag = ""
        if is_zt:
            has_zt_status = True
            limit_days = item.get('limit_days', 0)
            zt_tag = f"{limit_days}板" if limit_days > 0 else "首板"
            open_num = item.get('open_num', 0)
            if open_num > 0:
                zt_tag += f"/回封(炸{open_num}次)"
            elif item.get('is_first_limit'):
                zt_tag += "/硬板"

        # --- 2. 身份判定 (持仓/关注) ---
        manual_cleaned_tag = ""
        if code in manual_focus:
            is_selected = True
            if code in HOLDING_STRATEGIES:
                # 特殊策略，直接使用
                base_tags.append(HOLDING_STRATEGIES[code][0])
                manual_cleaned_tag = HOLDING_STRATEGIES[code][0]  # 记录下来用于去重
            elif code in holdings_map:
                t = f"持仓/{name}"
                base_tags.append(t)
                manual_cleaned_tag = t
            else:
                # F佬关注 - 进行深度清洗
                raw_note = f_lao_map[code]
                cleaned_note = clean_manual_tag(raw_note, has_zt_status)

                # 重新组装
                final_manual = f"F佬/{cleaned_note}" if cleaned_note != "关注" else "F佬/关注"
                base_tags.append(final_manual)
                manual_cleaned_tag = final_manual

        # --- 3. 标签组装 ---

        # 涨停标签
        if is_zt:
            is_selected = True
            base_tags.append(zt_tag)

        # 炸板
        is_zb = False
        if "炸板" in raw_tag_str:
            is_zb = True
        elif item.get('max_pct', 0) > 9.0 and pct < 9.0:
            is_zb = True

        if is_zb and pct > -7.0:
            is_selected = True
            base_tags.append("炸板/反包预期")

        # 跌停
        if pct <= -9.0:
            is_selected = True
            base_tags.append("📉跌停/博弈修复")

        # 大额成交 (补录)
        amount_yi = item.get('amount', 0) / 100000000.0
        if amount_yi > 20.0 and pct > 0:
            is_selected = True

        # --- 4. 最终合并 ---
        if is_selected:
            # 提取概念 (并去重)
            local_concepts = get_core_concepts_local(name, raw_tag_str)
            # 关键：从自动概念中剔除已经在手动标签里出现过的词
            unique_concepts = get_unique_concepts(manual_cleaned_tag, local_concepts)

            # 特殊形态
            shape_tags = check_special_shape(item)

            # 合并列表
            final_parts = []
            final_parts.extend(base_tags)
            if unique_concepts: final_parts.append(unique_concepts)
            final_parts.extend(shape_tags)

            # 简单去重 (防止完全一样的字符串重复)
            seen_parts = set()
            clean_parts = []
            for p in final_parts:
                if p not in seen_parts:
                    clean_parts.append(p)
                    seen_parts.add(p)

            final_tag_str = "/".join(clean_parts)

            # 再次清理可能产生的双斜杠
            final_tag_str = final_tag_str.replace('//', '/')

            row = {
                'sina_code': format_sina(code),
                'name': name,
                'tag': final_tag_str,
                'amount': item.get('amount', 0),
                'today_pct': pct,
                'turnover': item.get('turnover', 0),
                'open_pct': item.get('open_pct', 0),
                'price': item.get('price', 0),
                'pct_10': item.get('pct_10', 0),
                'link_dragon': get_link_dragon(code),
                'vol': item.get('vol', 0),
                'vol_prev': item.get('vol_prev', 0),
                'vol_ratio': item.get('vol_ratio', 0),
                'code': code
            }
            pool.append(row)

    # --- 5. 导出 ---
    if pool:
        df = pd.DataFrame(pool)
        df.sort_values(by='amount', ascending=False, inplace=True)

        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10',
                'link_dragon', 'vol', 'vol_prev', 'vol_ratio', 'code']
        for c in cols:
            if c not in df.columns: df[c] = 0
        df = df[cols]

        date_str = datetime.now().strftime("%Y%m%d")
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        save_path = os.path.join(ARCHIVE_DIR, f'strategy_pool_{date_str}.csv')
        latest_path = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')

        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        shutil.copyfile(save_path, latest_path)

        print(f"\n{Fore.GREEN}🎉 离线复盘完成！生成标的: {len(pool)} 只")
        print(f"📄 文件已保存: {latest_path}")

    else:
        print(f"{Fore.RED}❌ 筛选结果为空。")


if __name__ == "__main__":
    generate_strategy_pool()