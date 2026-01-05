# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (src/core/pool_generator_akshare.py) - v1.3.1 无损增强版
# ==============================================================================

import akshare as ak
import pandas as pd
from datetime import datetime
import os
import time
import sys
import re
import shutil
from colorama import init, Fore

# ================= 0. 环境初始化 =================
# 适配 Windows 控制台编码
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= 1. 路径与全局配置 =================

# --- 自动定位路径 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# --- 定义输入/输出文件路径 ---
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

print(f"{Fore.CYAN}🔧 项目根目录定位: {PROJECT_ROOT}")

# --- 策略参数配置 ---
TARGET_DATE = "today"

# 核心概念关键词 (用于自动打标签)
CORE_KEYWORDS = [
    '机器人', '航天', '军工', '卫星', '低空',
    'AI', '人工智能', '智能体', '算力', 'CPO', '存储',
    '消费电子', '华为', '信创', '数字货币', '数据要素',
    '文化传媒', '短剧', '多模态', '纺织', '并购重组', '固态电池', '自动驾驶'
]

# 板块中军挖掘列表
HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('AI智能体', 'concept'),
    ('消费电子', 'industry'),
    ('低空经济', 'concept'),
    ('数字货币', 'concept'),
    ('文化传媒', 'industry'),
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

# 全局缓存
CONCEPT_CACHE = {}


# ================= 2. 数据加载函数 (Parsers) =================

def load_f_lao_list():
    """从 txt 文件加载 F佬/手动关注列表"""
    f_list = {}
    if not os.path.exists(F_LAO_PATH):
        print(f"{Fore.YELLOW}⚠️ 未找到F佬列表文件: {F_LAO_PATH} (将使用空列表){Fore.RESET}")
        return f_list

    try:
        with open(F_LAO_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"{Fore.MAGENTA}📖 正在加载F佬/手动策略列表...{Fore.RESET}")
        count = 0
        for line in lines:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue

            # 按空格或制表符分割
            parts = re.split(r'\s+', line, maxsplit=1)
            if len(parts) < 2:
                continue

            code = parts[0].strip()
            tag = parts[1].strip()

            # 简单校验代码格式 (6位数字)
            if code.isdigit() and len(code) == 6:
                f_list[code] = tag
                count += 1

        print(f"   ↳ 成功加载 {count} 个重点标的")
        return f_list

    except Exception as e:
        print(f"{Fore.RED}❌ 读取F佬列表失败: {e}{Fore.RESET}")
        return {}


def parse_holdings_text():
    """解析持仓文件"""
    if not os.path.exists(HOLDINGS_PATH):
        print(f"{Fore.YELLOW}⚠️ 未找到持仓文件: {HOLDINGS_PATH}{Fore.RESET}")
        return {}

    holdings = {}
    try:
        with open(HOLDINGS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or "证券代码" in line or "合计" in line: continue
            parts = re.split(r'\s+', line)
            if len(parts) < 3: continue
            code = parts[0]
            name = parts[1]
            if code in HOLDING_STRATEGIES:
                tag = HOLDING_STRATEGIES[code][0]
            else:
                tag = f"持仓/{name}"
            holdings[code] = tag
        print(f"{Fore.CYAN}📂 银河持仓加载: {len(holdings)} 只{Fore.RESET}")
        return holdings
    except Exception as e:
        print(f"{Fore.RED}❌ 读取持仓失败: {e}{Fore.RESET}")
        return {}


def parse_ths_clipboard():
    """解析同花顺剪贴板"""
    if not os.path.exists(THS_PATH):
        print(f"{Fore.YELLOW}⚠️ 未找到同花顺文件: {THS_PATH}{Fore.RESET}")
        return {}

    ths_pool = {}
    print(f"{Fore.MAGENTA}📂 同花顺剪贴板加载...{Fore.RESET}")
    try:
        # 优先尝试 UTF-8
        with open(THS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 失败则尝试 GBK
        print(f"{Fore.YELLOW}ℹ️ 已切换为 GBK 编码读取同花顺文件{Fore.RESET}")
        with open(THS_PATH, 'r', encoding='gbk') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"{Fore.RED}❌ 读取同花顺文件失败: {e}{Fore.RESET}")
        return {}

    for line in lines:
        line = line.strip()
        if not line or "代码" in line: continue
        parts = re.split(r'\s+', line)
        if len(parts) < 2: continue

        raw_code = parts[0]
        name = parts[1]
        clean_code = raw_code.replace("SZ", "").replace("SH", "")

        if not clean_code.isdigit() or len(clean_code) != 6: continue
        tag = f"同花顺/{name}"
        ths_pool[clean_code] = tag

    print(f"{Fore.BLUE}✅ 同花顺数据: {len(ths_pool)} 只{Fore.RESET}")
    return ths_pool


# ================= 3. 核心工具函数 (Helpers) =================

def get_target_date_str():
    if TARGET_DATE == "today":
        return datetime.now().strftime("%Y%m%d")
    return TARGET_DATE


def format_sina(code):
    code = str(code)
    if code.startswith('6'): return f"sh{code}"
    if code.startswith('8') or code.startswith('4'): return f"bj{code}"
    return f"sz{code}"


def get_link_dragon(code):
    """获取关联的大哥代码"""
    # 1. 优先查持仓策略配置
    if code in HOLDING_STRATEGIES:
        dragon = HOLDING_STRATEGIES[code][1]
        if dragon: return dragon

    # 2. 查通用映射表
    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon:
        if dragon.startswith('sz') or dragon.startswith('sh'): return dragon
        return format_sina(dragon)
    return ''


def get_core_concepts(code, name):
    """获取股票核心概念 (带缓存)"""
    if code in CONCEPT_CACHE:
        return CONCEPT_CACHE[code]

    matched_concepts = set()
    try:
        # 获取个股所属概念板块 (东方财富接口)
        df = ak.stock_board_concept_name_em(symbol=code)
        if df is not None and not df.empty:
            all_concepts = df['板块名称'].tolist()
            # 过滤出我们关心的核心关键词
            for c in all_concepts:
                for key in CORE_KEYWORDS:
                    if key in c:
                        matched_concepts.add(c)
    except:
        pass

    result = "/".join(list(matched_concepts))
    CONCEPT_CACHE[code] = result
    if result:
        print(f"   ↳ {name} 命中概念: {result}")
    return result


def get_market_data(code):
    """
    获取单只股票的行情快照
    [v1.3 增强] 新增成交额(amount)获取
    """
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df.empty or len(df) < 2: return None

        last_row = df.iloc[-1]  # 最后一个交易日（今日）
        prev_row = df.iloc[-2]  # 倒数第二个交易日（昨日）
        current_price = last_row['收盘']

        turnover = last_row.get('换手率', 0)

        # 计算10日涨幅
        if len(df) > 11:
            base_10 = df.iloc[-11]['收盘']
            pct_10 = (current_price - base_10) / base_10 * 100
        else:
            pct_10 = 0

        # [修改] 计算量比逻辑
        vol_current = last_row['成交量']
        vol_prev = prev_row['成交量']
        vol_ratio = round(vol_current / vol_prev, 2) if vol_prev > 0 else 0

        # [v1.3 新增] 获取成交额 (单位: 元)
        amt_current = float(last_row['成交额'])

        return {
            'vol': vol_current,
            'amount': amt_current,  # 新增字段
            'vol_prev': vol_prev,
            'vol_ratio': vol_ratio,
            'pct_10': round(pct_10, 2),
            'price': current_price,
            'open_pct': round((last_row['开盘'] - prev_row['收盘']) / prev_row['收盘'] * 100, 2),
            'today_pct': round(last_row['涨跌幅'], 2),
            'turnover': round(float(turnover), 2),
            'high': last_row['最高'],
            'low': last_row['最低'],
            'prev_close': prev_row['收盘']
        }
    except Exception as e:
        # print(f"获取行情失败 {code}: {e}") # 调试用
        return None


def check_special_shape(m_data):
    """
    检查特殊形态 (地天板/20cm)
    [v1.3 增强] 新增资金面打标 (大战场/流动性差)
    """
    tags = []
    if m_data:
        low_pct = (m_data['low'] - m_data['prev_close']) / m_data['prev_close'] * 100
        if low_pct < -9.0 and m_data['today_pct'] > 9.0:
            tags.append("🔥地天板")
        if m_data['today_pct'] > 14.0:
            tags.append("🔥20cm")

        # [v1.3 新增] 资金标签
        # 昨成交额 > 20亿 -> 大战场
        amt_yi = m_data['amount'] / 100000000
        if amt_yi > 20.0:
            tags.append("💰大战场")
        # 昨成交额 < 0.5亿 -> 流动性差
        elif amt_yi < 0.5:
            tags.append("⚠️流动性差")

    return tags


def add_sector_leaders(strategy_rows, seen_codes):
    """挖掘板块中军逻辑"""
    print(f"\n{Fore.MAGENTA}🔎 挖掘板块中军 (成交额Top2)...{Fore.RESET}")
    for concept_info in HOT_CONCEPTS:
        concept, board_type = concept_info
        try:
            if board_type == 'industry':
                df = ak.stock_board_industry_cons_em(symbol=concept)
            else:
                df = ak.stock_board_concept_cons_em(symbol=concept)

            if df is None or df.empty: continue

            # 取成交额前2名
            df = df.sort_values(by='成交额', ascending=False).head(2)

            for _, row in df.iterrows():
                code, name = row['代码'], row['名称']
                tag_suffix = f"/{concept}中军"

                # 如果已经在池子里，追加标签
                if code in seen_codes:
                    for item in strategy_rows:
                        if item['code'] == code:
                            if tag_suffix not in item['tag']:
                                item['tag'] += tag_suffix
                                print(f"追加标签: {name} -> {item['tag']}")
                    continue

                # 如果不在，新增入池
                m_data = get_market_data(code)
                if m_data:
                    final_tag = f"{concept}中军"
                    extra_concepts = get_core_concepts(code, name)
                    if extra_concepts:
                        final_tag += f"/{extra_concepts}"

                    strategy_rows.append({
                        'code': code, 'name': name, 'tag': final_tag,
                        'link_dragon': get_link_dragon(code),
                        'vol': int(m_data['vol']),  # 强转int
                        'amount': m_data['amount'],  # 新增
                        'vol_prev': int(m_data['vol_prev']),
                        'vol_ratio': m_data.get('vol_ratio', 0),
                        'pct_10': m_data['pct_10'],
                        'price': m_data['price'],
                        'open_pct': m_data['open_pct'],
                        'today_pct': m_data['today_pct'],
                        'turnover': m_data['turnover']
                    })
                    seen_codes.add(code)
                    amt_yi = round(m_data['amount'] / 100000000, 2)
                    print(f"入池: {name} 额:{amt_yi}亿 ({final_tag})")
            time.sleep(0.5)  # 防封
        except Exception as e:
            pass


# ================= 4. 主逻辑 (Main Logic) =================

def generate_csv():
    # 确保输出目录存在
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    date_str = get_target_date_str()
    print(f"{Fore.CYAN}⏳ 启动复盘生成 | 目标日期: {date_str} ...{Fore.RESET}")

    strategy_rows = []
    seen_codes = set()

    # --- 加载各类数据源 ---
    my_holdings = parse_holdings_text()
    my_ths_list = parse_ths_clipboard()
    f_lao_list = load_f_lao_list()  # 在此处调用加载，避免全局污染

    # 合并手动关注列表
    combined_manual_list = my_ths_list.copy()
    combined_manual_list.update(f_lao_list)
    combined_manual_list.update(my_holdings)

    # 内部辅助函数：添加单条记录
    def add_item(code, name, base_tag, zt_turnover=None):
        if code in seen_codes: return
        m_data = get_market_data(code)
        if m_data:
            final_turnover = zt_turnover if zt_turnover else m_data['turnover']
            extra_concepts = get_core_concepts(code, name)

            special_tags = check_special_shape(m_data)
            tag_list = [base_tag]
            if extra_concepts: tag_list.append(extra_concepts)
            tag_list.extend(special_tags)

            final_tag = "/".join(tag_list)

            strategy_rows.append({
                'code': code, 'name': name, 'tag': final_tag,
                'link_dragon': get_link_dragon(code),
                'vol': int(m_data['vol']),  # 强转int
                'amount': m_data['amount'],  # 新增
                'vol_prev': int(m_data['vol_prev']),
                'vol_ratio': m_data.get('vol_ratio', 0),
                'pct_10': m_data['pct_10'],
                'price': m_data['price'],
                'open_pct': m_data['open_pct'],
                'today_pct': m_data['today_pct'],
                'turnover': final_turnover
            })
            seen_codes.add(code)
            amt_yi = round(m_data['amount'] / 100000000, 2)
            print(f"入池: {name:<8} 额:{amt_yi}亿 ({final_tag})")

    # --- 步骤 1: 抓取涨停 ---
    print(f"\n{Fore.YELLOW}[1/5] 抓取涨停数据 ({date_str})...{Fore.RESET}")
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                open_num = row['炸板次数']
                is_first_limit = row['首次封板时间'] == row['最后封板时间']
                zt_turnover = row.get('换手率', 0)

                tag = f"{row['连板数']}板"
                if open_num > 0:
                    tag += f"/回封(炸{open_num}次)"
                elif is_first_limit:
                    tag += "/硬板(无炸)"
                else:
                    tag += "/强势"
                add_item(row['代码'], row['名称'], tag, zt_turnover)
        else:
            print(f"{Fore.RED}⚠️ 未获取到涨停数据{Fore.RESET}")
    except Exception as e:
        print(f"获取涨停数据失败: {e}")

    # --- 步骤 2: 抓取炸板 ---
    print(f"\n{Fore.YELLOW}[2/5] 抓取炸板数据 ({date_str})...{Fore.RESET}")
    try:
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if not df_zb.empty:
            for _, row in df_zb.iterrows():
                zb_turnover = row.get('换手率', None)
                add_item(row['代码'], row['名称'], "炸板/反包预期", zb_turnover)
    except:
        pass

    # --- 步骤 3: 抓取跌停 ---
    print(f"\n{Fore.YELLOW}[3/5] 抓取跌停数据 ({date_str})...{Fore.RESET}")
    try:
        df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        if not df_dt.empty:
            for _, row in df_dt.iterrows():
                dt_turnover = row.get('换手率', None)
                add_item(row['代码'], row['名称'], "跌停/博弈修复", dt_turnover)
    except:
        pass

    # --- 步骤 4: 板块中军 ---
    print(f"\n{Fore.YELLOW}[4/5] 挖掘板块中军 (实时)...{Fore.RESET}")
    add_sector_leaders(strategy_rows, seen_codes)

    # --- 步骤 5: 注入持仓与关注 ---
    print(f"\n{Fore.YELLOW}[5/5] 注入持仓与F佬关注列表...{Fore.RESET}")
    for code, tag in combined_manual_list.items():
        if code in seen_codes:
            # 已经在池中（例如涨停了），则更新标签
            for item in strategy_rows:
                if item['code'] == code:
                    orig_tag = item['tag']
                    board_info = orig_tag.split('/')[0] if '板' in orig_tag.split('/')[0] else ''

                    special_tags = [x for x in orig_tag.split('/') if "🔥" in x or "💰" in x or "⚠️" in x]  # [v1.3] 保留新标签
                    existing_concepts = [x for x in orig_tag.split('/') if
                                         x in CORE_KEYWORDS or any(k in x for k in CORE_KEYWORDS)]

                    new_tag_parts = []
                    if board_info: new_tag_parts.append(board_info)
                    new_tag_parts.append(tag)  # 插入手动标签
                    new_tag_parts.extend(existing_concepts)
                    new_tag_parts.extend(special_tags)

                    if "回封" in orig_tag:
                        new_tag_parts.append("回封")
                    elif "硬板" in orig_tag:
                        new_tag_parts.append("硬板")
                    elif "炸板" in orig_tag:
                        new_tag_parts.append("炸板")

                    item['tag'] = "/".join(list(dict.fromkeys(new_tag_parts)))  # 去重
                    item['link_dragon'] = get_link_dragon(code)
                    print(f"更新标签: {item['name']} -> {item['tag']}")
                    break
        else:
            # 不在池中，新增
            try:
                name_guess = tag.split('/')[1].split('(')[0] if '/' in tag else "关注"
                add_item(code, name_guess, tag)
            except:
                add_item(code, "关注", tag)

    # --- 结果导出 ---
    if strategy_rows:
        df_save = pd.DataFrame(strategy_rows)
        df_save['sina_code'] = df_save['code'].apply(format_sina)

        # [v1.3 修改] 优先按 amount (资金) 降序排列，大资金在前
        df_save.sort_values(by='amount', ascending=False, inplace=True)

        # [v1.3 修改] 更新列名，加入 amount
        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10',
                'link_dragon',
                'vol', 'vol_prev', 'vol_ratio', 'code']
        df_save = df_save.reindex(columns=cols)

        # 1. 保存到历史存档
        filename_dated = f'strategy_pool_{date_str}.csv'
        save_path_dated = os.path.join(ARCHIVE_DIR, filename_dated)
        df_save.to_csv(save_path_dated, index=False, encoding='utf-8-sig')
        print(f"\n✅ 历史存档已生成: {save_path_dated} ({len(df_save)} 只)")

        # 2. 覆盖最新文件（供监控脚本读取）
        latest_path = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')
        shutil.copyfile(save_path_dated, latest_path)
        print(f"✅ 监控链接已更新: {latest_path}")


# ================= 5. 程序入口 =================

if __name__ == "__main__":
    generate_csv()