# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (src/core/pool_generator.py) - v1.2.0 路径增强版
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

if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 (自动定位) =================
# 获取当前脚本所在目录 (src/core)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 向推两级找到项目根目录 (stock_fupan_tools)
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# 定义绝对路径
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

# 确保输出目录存在
os.makedirs(ARCHIVE_DIR, exist_ok=True)

print(f"{Fore.CYAN}🔧 项目根目录定位: {PROJECT_ROOT}")

# ================= ⚙️ 策略配置区 =================

TARGET_DATE = "today"

# 🔥 定义我们要重点捕获的概念关键词
CORE_KEYWORDS = [
    '机器人', '航天', '军工', '卫星', '低空',
    'AI', '人工智能', '智能体', '算力', 'CPO', '存储',
    '消费电子', '华为', '信创', '数字货币', '数据要素',
    '文化传媒', '短剧', '多模态', '纺织'
]

# 用于挖掘中军的板块列表
HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('AI智能体', 'concept'),
    ('消费电子', 'industry'),
    ('低空经济', 'concept'),
    ('数字货币', 'concept'),
    ('文化传媒', 'industry'),
]

# 🔥 F佬/论坛 手动池
F_LAO_LIST = {
    '002201': 'F佬/九鼎(地天板/航天)',
    '600118': 'F佬/卫通(千亿中军)',
    '603278': 'F佬/大业(机器人/航天/6板)',
    '002347': 'F佬/泰尔(机器人/航天/弱转强)',
    '002931': 'F佬/锋龙(航天/5板)',
    '603667': 'F佬/五洲(机器人/航天)',
    '000665': 'F佬/湖北广电(AI智能体龙头)',
    '002757': 'F佬/南兴(AI套利/机器人)',
    '300058': 'NGA/蓝光(AI智能体/20cm)',
    '301066': 'NGA/万事利(AI应用/春晚IP/20cm)',
    '301153': 'NGA/中科江南(数字货币/数据要素)',
    '002908': 'NGA/德生科技(数字货币/社保)',
    '002177': 'F佬/御银(数字货币/死亡换手)',
    '002050': 'F佬/三花(机器人中军)',
    '002009': 'F佬/天奇(被泰尔卡位)',
    '000559': 'NGA/万向钱潮(量化拉升/反包预期)',
    '603130': 'NGA/云中马(马字辈/纺织)',
    '603123': 'F佬/翠微(数字货币/炸板)',
}

HOLDING_STRATEGIES = {
    '603667': ('持仓/五洲(机器人/航天)', ''),
    '300115': ('持仓/长盈(消电中军)', 'sz002475'),
    '300223': ('持仓/君正(存储)', ''),
    '001231': ('持仓/农心(农业)', ''),
    '002703': ('持仓/世宝(需红开)', ''),
    '600755': ('持仓/国贸(博弈修复)', ''),
}

LINK_DRAGON_MAP = {
    '002009': '002931',
}

# 缓存概念数据，避免重复请求
CONCEPT_CACHE = {}


# ================= 🛠️ 工具函数 =================

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
    if code in HOLDING_STRATEGIES:
        dragon = HOLDING_STRATEGIES[code][1]
        if dragon: return dragon
    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon:
        if dragon.startswith('sz') or dragon.startswith('sh'): return dragon
        return format_sina(dragon)
    return ''


def get_core_concepts(code, name):
    """获取股票核心概念"""
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
        # 尝试 UTF-8
        try:
            with open(THS_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 尝试 GBK
            with open(THS_PATH, 'r', encoding='gbk') as f:
                lines = f.readlines()
            print(f"{Fore.YELLOW}ℹ️ 已切换为 GBK 编码读取{Fore.RESET}")

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
    except Exception as e:
        print(f"{Fore.RED}❌ 读取同花顺文件失败: {e}{Fore.RESET}")
        return {}


def get_market_data(code):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df.empty or len(df) < 2: return None
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        current_price = last_row['收盘']

        turnover = 0
        if '换手率' in last_row:
            turnover = last_row['换手率']

        if len(df) > 11:
            base_10 = df.iloc[-11]['收盘']
            pct_10 = (current_price - base_10) / base_10 * 100
        else:
            pct_10 = 0

        return {
            'vol': last_row['成交量'],
            'pct_10': round(pct_10, 2),
            'price': current_price,
            'open_pct': round((last_row['开盘'] - prev_row['收盘']) / prev_row['收盘'] * 100, 2),
            'today_pct': round(last_row['涨跌幅'], 2),
            'turnover': round(float(turnover), 2),
            'high': last_row['最高'],
            'low': last_row['最低'],
            'prev_close': prev_row['收盘']
        }
    except:
        return None


def check_special_shape(m_data):
    tags = []
    if m_data:
        low_pct = (m_data['low'] - m_data['prev_close']) / m_data['prev_close'] * 100
        if low_pct < -9.0 and m_data['today_pct'] > 9.0:
            tags.append("🔥地天板")
        if m_data['today_pct'] > 14.0:
            tags.append("🔥20cm")
    return tags


def add_sector_leaders(strategy_rows, seen_codes):
    print(f"\n{Fore.MAGENTA}🔎 挖掘板块中军 (成交额Top2)...{Fore.RESET}")
    for concept_info in HOT_CONCEPTS:
        concept, board_type = concept_info
        try:
            if board_type == 'industry':
                df = ak.stock_board_industry_cons_em(symbol=concept)
            else:
                df = ak.stock_board_concept_cons_em(symbol=concept)
            if df is None or df.empty: continue

            df = df.sort_values(by='成交额', ascending=False).head(2)

            for _, row in df.iterrows():
                code, name = row['代码'], row['名称']
                tag_suffix = f"/{concept}中军"

                if code in seen_codes:
                    for item in strategy_rows:
                        if item['code'] == code:
                            if tag_suffix not in item['tag']:
                                item['tag'] += tag_suffix
                                print(f"追加标签: {name} -> {item['tag']}")
                    continue

                m_data = get_market_data(code)
                if m_data:
                    final_tag = f"{concept}中军"
                    extra_concepts = get_core_concepts(code, name)
                    if extra_concepts:
                        final_tag += f"/{extra_concepts}"

                    strategy_rows.append({
                        'code': code, 'name': name, 'tag': final_tag,
                        'link_dragon': get_link_dragon(code),
                        'vol': m_data['vol'],
                        'pct_10': m_data['pct_10'],
                        'price': m_data['price'],
                        'open_pct': m_data['open_pct'],
                        'today_pct': m_data['today_pct'],
                        'turnover': m_data['turnover']
                    })
                    seen_codes.add(code)
                    print(f"入池: {name} ({final_tag})")
            time.sleep(0.5)
        except Exception as e:
            pass


# ================= 🚀 主程序 =================

def generate_csv():
    date_str = get_target_date_str()
    print(f"{Fore.CYAN}⏳ 启动复盘生成 | 目标日期: {date_str} ...{Fore.RESET}")

    strategy_rows = []
    seen_codes = set()

    my_holdings = parse_holdings_text()
    my_ths_list = parse_ths_clipboard()

    combined_manual_list = my_ths_list.copy()
    combined_manual_list.update(F_LAO_LIST)
    combined_manual_list.update(my_holdings)

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
                'vol': m_data['vol'],
                'pct_10': m_data['pct_10'],
                'price': m_data['price'],
                'open_pct': m_data['open_pct'],
                'today_pct': m_data['today_pct'],
                'turnover': final_turnover
            })
            seen_codes.add(code)
            print(f"入池: {name:<8} ({final_tag})")

    # --- 1. 抓取涨停 ---
    print(f"\n{Fore.YELLOW}[1/5] 抓取涨停数据 ({date_str})...{Fore.RESET}")
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                open_num = row['炸板次数']
                is_first_limit = row['首次封板时间'] == row['最后封板时间']
                zt_turnover = row['换手率'] if '换手率' in row else 0

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

    # --- 2. 抓取炸板 ---
    print(f"\n{Fore.YELLOW}[2/5] 抓取炸板数据 ({date_str})...{Fore.RESET}")
    try:
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if not df_zb.empty:
            for _, row in df_zb.iterrows():
                zb_turnover = row['换手率'] if '换手率' in row else None
                add_item(row['代码'], row['名称'], "炸板/反包预期", zb_turnover)
    except:
        pass

    # --- 3. 抓取跌停 ---
    print(f"\n{Fore.YELLOW}[3/5] 抓取跌停数据 ({date_str})...{Fore.RESET}")
    try:
        df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        if not df_dt.empty:
            for _, row in df_dt.iterrows():
                dt_turnover = row['换手率'] if '换手率' in row else None
                add_item(row['代码'], row['名称'], "跌停/博弈修复", dt_turnover)
    except:
        pass

    # --- 4. 板块中军 ---
    print(f"\n{Fore.YELLOW}[4/5] 挖掘板块中军 (实时)...{Fore.RESET}")
    add_sector_leaders(strategy_rows, seen_codes)

    # --- 5. 注入关注 ---
    print(f"\n{Fore.YELLOW}[5/5] 注入持仓与关注...{Fore.RESET}")
    for code, tag in combined_manual_list.items():
        if code in seen_codes:
            for item in strategy_rows:
                if item['code'] == code:
                    orig_tag = item['tag']
                    board_info = orig_tag.split('/')[0] if '板' in orig_tag.split('/')[0] else ''

                    special_tags = [x for x in orig_tag.split('/') if "🔥" in x]
                    existing_concepts = [x for x in orig_tag.split('/') if
                                         x in CORE_KEYWORDS or any(k in x for k in CORE_KEYWORDS)]

                    new_tag_parts = []
                    if board_info: new_tag_parts.append(board_info)
                    new_tag_parts.append(tag)
                    new_tag_parts.extend(existing_concepts)
                    new_tag_parts.extend(special_tags)

                    if "回封" in orig_tag:
                        new_tag_parts.append("回封")
                    elif "硬板" in orig_tag:
                        new_tag_parts.append("硬板")
                    elif "炸板" in orig_tag:
                        new_tag_parts.append("炸板")

                    item['tag'] = "/".join(list(dict.fromkeys(new_tag_parts)))
                    item['link_dragon'] = get_link_dragon(code)
                    print(f"更新标签: {item['name']} -> {item['tag']}")
                    break
        else:
            try:
                name_guess = tag.split('/')[1].split('(')[0] if '/' in tag else "关注"
                add_item(code, name_guess, tag)
            except:
                add_item(code, "关注", tag)

    if strategy_rows:
        df_save = pd.DataFrame(strategy_rows)
        df_save['sina_code'] = df_save['code'].apply(format_sina)
        cols = ['sina_code', 'name', 'tag', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10', 'link_dragon',
                'vol', 'code']
        df_save = df_save.reindex(columns=cols)

        df_save.sort_values(by=['tag'], ascending=False, inplace=True)

        # 保存到存档目录
        filename_dated = f'strategy_pool_{date_str}.csv'
        save_path_dated = os.path.join(ARCHIVE_DIR, filename_dated)

        df_save.to_csv(save_path_dated, index=False, encoding='utf-8-sig')
        print(f"\n✅ 历史存档已生成: {save_path_dated} ({len(df_save)} 只)")

        # 复制到最新文件（供监控脚本使用）
        latest_path = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')
        shutil.copyfile(save_path_dated, latest_path)
        print(f"✅ 监控链接已更新: {latest_path}")


if __name__ == "__main__":
    generate_csv()