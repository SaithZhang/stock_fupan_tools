# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (src/core/pool_generator.py)
#    逻辑同步版本: v1.3.1 (对齐 pool_generator_akshare.py)
# ==============================================================================

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


def get_core_concepts_local(name, raw_tag):
    """
    本地提取核心概念
    (由于没有实时API，主要依赖名字和原始Tag中的关键字)
    """
    matched = set()
    source_text = f"{name} {raw_tag}"

    for key in CORE_KEYWORDS:
        if key in source_text:
            matched.add(key)

    return "/".join(list(matched))


def check_special_shape(item):
    """
    检查特殊形态 (地天板/20cm/资金面)
    逻辑与 pool_generator_akshare.py 保持完全一致
    """
    tags = []
    pct = item.get('today_pct', 0)
    low_pct = 0  # 需要数据源支持，如果只有收盘价，这部分可能不准

    # 尝试计算 low_pct (如果有数据)
    if 'low' in item and 'prev_close' in item and item['prev_close'] > 0:
        low_pct = (item['low'] - item['prev_close']) / item['prev_close'] * 100

    # 1. 地天板
    if low_pct < -9.0 and pct > 9.0:
        tags.append("🔥地天板")
    # 2. 20cm
    if pct > 14.0:
        tags.append("🔥20cm")

    # 3. 资金面标签
    amount_val = item.get('amount', 0)
    amt_yi = amount_val / 100000000.0

    if amt_yi > 20.0:
        tags.append("💰大战场")
    elif amt_yi < 0.5 and amt_yi > 0:  # 排除0成交额的停牌股
        tags.append("⚠️流动性差")

    return tags


# ================= 3. 主生成逻辑 =================

def generate_strategy_pool():
    # 1. 获取全量数据 (由 data_loader 提供)
    all_data = get_merged_data()
    if not all_data:
        print(f"{Fore.RED}❌ 数据源为空，请检查 data_loader")
        return

    # 2. 加载手动名单
    holdings_map = load_text_list(HOLDINGS_PATH)
    f_lao_map = load_text_list(F_LAO_PATH)

    # 合并关注名单 (持仓优先)
    manual_focus = f_lao_map.copy()
    manual_focus.update(holdings_map)  # update会覆盖重复key，持仓覆盖F佬

    print(f"{Fore.CYAN}📋 离线生成启动 | 数据源: {len(all_data)}条 | 持仓: {len(holdings_map)} | 关注: {len(f_lao_map)}")

    pool = []
    seen_codes = set()

    # 3. 遍历筛选 (逻辑对齐 akshare 版)
    for item in all_data:
        code = str(item['code'])
        name = item['name']
        pct = item.get('today_pct', 0)

        # 基础数据清洗
        raw_tag_str = str(item.get('tag', ''))
        if 'nan' in raw_tag_str: raw_tag_str = ""

        # --- 判定核心身份 (Base Tag) ---
        base_tags = []
        is_selected = False

        # A. 持仓/关注 (最高优先级)
        if code in manual_focus:
            is_selected = True
            # 如果是持仓，且有特殊策略配置
            if code in HOLDING_STRATEGIES:
                base_tags.append(HOLDING_STRATEGIES[code][0])
            elif code in holdings_map:
                base_tags.append(f"持仓/{name}")
            else:
                # F佬关注
                note = f_lao_map[code]
                base_tags.append(f"F佬/{note}" if note != "关注" else "F佬/关注")

        # B. 涨停 (Limit Up)
        # 判断逻辑：is_zt 标记 或 涨幅接近涨停价
        is_zt = item.get('is_zt') or (pct >= 9.8)  # 简单兜底
        if is_zt:
            is_selected = True
            # 尝试解析连板数
            limit_days = item.get('limit_days', 0)
            zt_tag = f"{limit_days}板" if limit_days > 0 else "首板"

            # 炸板次数回封逻辑 (如果 data_loader 提供了 open_num)
            open_num = item.get('open_num', 0)
            if open_num > 0:
                zt_tag += f"/回封(炸{open_num}次)"
            elif item.get('is_first_limit'):  # 如果有首次封板标识
                zt_tag += "/硬板"

            base_tags.append(zt_tag)

        # C. 炸板 (Broken Limit)
        # 逻辑：最高价摸板但收盘未板，且没跌太多
        # data_loader 如果有 max_pct 字段最好，没有则依赖 tag 字段包含'炸板'
        is_zb = False
        if "炸板" in raw_tag_str:
            is_zb = True
        elif item.get('max_pct', 0) > 9.0 and pct < 9.0:
            is_zb = True

        if is_zb and pct > -7.0:  # 深水炸板不算反包预期，算核按钮
            is_selected = True
            base_tags.append("炸板/反包预期")

        # D. 跌停 (Limit Down)
        if pct <= -9.0:
            is_selected = True
            base_tags.append("跌停/博弈修复")

        # E. 板块中军 (基于成交额的补录)
        # akshare版是实时抓取，这里只能基于金额补录
        amount_yi = item.get('amount', 0) / 100000000.0
        if amount_yi > 20.0 and pct > 0:
            # 即使没涨停，大成交额红盘也是观测点
            is_selected = True
            # 标签在后面统一加 "💰大战场"

        # --- 组装最终标签 ---
        if is_selected:
            # 1. 提取核心概念 (本地匹配)
            concept_tag = get_core_concepts_local(name, raw_tag_str)

            # 2. 计算特殊形态 (大战场/地天板)
            shape_tags = check_special_shape(item)

            # 3. 合并所有标签
            final_parts = []
            final_parts.extend(base_tags)
            if concept_tag: final_parts.append(concept_tag)
            final_parts.extend(shape_tags)

            # 4. 去重并清理
            # 保持顺序去重
            seen_parts = set()
            clean_parts = []
            for p in final_parts:
                if p not in seen_parts:
                    clean_parts.append(p)
                    seen_parts.add(p)

            final_tag_str = "/".join(clean_parts)

            # 构造输出行
            # 字段顺序严格对齐 akshare 版
            row = {
                'sina_code': format_sina(code),
                'name': name,
                'tag': final_tag_str,
                'amount': item.get('amount', 0),  # 核心排序依据
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

    # --- 4. 导出与保存 ---
    if pool:
        df = pd.DataFrame(pool)

        # [核心修改] 排序逻辑对齐：按成交额降序 (大战场优先)
        df.sort_values(by='amount', ascending=False, inplace=True)

        # 确保列顺序一致
        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10',
                'link_dragon', 'vol', 'vol_prev', 'vol_ratio', 'code']
        # 防止 key error，补齐缺少的列
        for c in cols:
            if c not in df.columns: df[c] = 0

        df = df[cols]

        # 保存
        date_str = datetime.now().strftime("%Y%m%d")
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        save_path = os.path.join(ARCHIVE_DIR, f'strategy_pool_{date_str}.csv')
        latest_path = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')

        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        shutil.copyfile(save_path, latest_path)

        print(f"\n{Fore.GREEN}🎉 离线复盘完成！生成标的: {len(pool)} 只")
        print(f"   ↳ 排序依据: 成交额(Amount) 降序")
        print(f"📄 文件已保存: {latest_path}")

    else:
        print(f"{Fore.RED}❌ 筛选结果为空，请检查输入数据。")


if __name__ == "__main__":
    generate_strategy_pool()