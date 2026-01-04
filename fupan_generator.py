# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (fupan_generator.py) - 历史存档版
# ==============================================================================
# 更新日志：
# 1. [文件存档] 自动生成带日期的CSV (如 strategy_pool_20231231.csv)。
# 2. [默认链接] 同时更新 strategy_pool.csv 供监控脚本读取。
# 3. [日期配置] 支持 TARGET_DATE 配置，可手动抓取历史日期的涨停数据。
# 4. [双轨读取] 支持 holdings.txt 和 ths_clipboard.txt。
# ==============================================================================

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import os
import time
import sys
import re
import shutil  # 用于复制文件
from colorama import init, Fore

if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 配置区 =================

# 🔥 目标日期配置 (默认为 "today")
# 如果想复盘昨天，填入具体日期，例如: "20231229"
# 如果填 "today"，则自动获取当前日期
TARGET_DATE = "today"

HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('AI智能体', 'concept'),
    ('消费电子', 'industry'),  # ⬅️ 修改点：去掉了"概念"后缀，类型改为 industry
    ('低空经济', 'concept'),
]

F_LAO_LIST = {
    '002201': 'F佬/九鼎(地天板/航天)',
    '000665': 'F佬/湖北广电(AI智能体龙头)',
    '002757': 'F佬/南兴(AI套利)',
    '600728': 'F佬/佳都(AI套利)',
    '002347': 'F佬/泰尔(机器人/航天双属性)',
    '603667': 'F佬/五洲(机器人/航天)',
    '603278': 'F佬/大业(机器人/航天)',
    '002009': 'F佬/天奇(锋龙补涨/弱转强)',
    '002050': 'F佬/三花(机器人中军)',
    '002471': 'F佬/中超(断板反包预期)',
    '002177': 'F佬/御银(弱转强)',
    '600118': 'F佬/卫通(千亿中军)',
    '603123': 'F佬/翠微(炸板/需弱转强)',
    '002703': 'F佬/世宝(需红开)',
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


# ========================================================================

def get_target_date_str():
    """获取格式化的目标日期字符串 YYYYMMDD"""
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


def parse_holdings_text():
    file_path = 'holdings.txt'
    if not os.path.exists(file_path): return {}
    holdings = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or "证券代码" in line or "合计" in line: continue
            parts = re.split(r'\s+', line)
            if len(parts) < 3: continue
            code = parts[0]
            name = parts[1]
            try:
                if float(parts[2]) <= 0: continue
            except:
                continue

            if code in HOLDING_STRATEGIES:
                tag = HOLDING_STRATEGIES[code][0]
            else:
                tag = f"持仓/{name}"
            holdings[code] = tag
        print(f"{Fore.CYAN}📂 银河持仓加载: {len(holdings)} 只{Fore.RESET}")
        return holdings
    except Exception as e:
        print(f"{Fore.RED}❌ 读取 holdings.txt 失败: {e}{Fore.RESET}")
        return {}


def parse_ths_clipboard():
    file_path = 'ths_clipboard.txt'
    if not os.path.exists(file_path): return {}
    ths_pool = {}
    print(f"{Fore.MAGENTA}📂 同花顺剪贴板加载...{Fore.RESET}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
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
        print(f"{Fore.RED}❌ 读取 ths_clipboard.txt 失败: {e}{Fore.RESET}")
        return {}


def get_market_data(code):
    try:
        # 注意：这里获取的是【最新】的实时/历史行情
        # 如果 TARGET_DATE 是过去日期，这里的 "today_pct" 依然会取到最新一天的
        # 若要完全回测历史状态比较复杂，这里仅作为复盘选股工具，默认取最新状态
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df.empty or len(df) < 2: return None
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        current_price = last_row['收盘']
        if len(df) > 11:
            base_10 = df.iloc[-11]['收盘']
            pct_10 = (current_price - base_10) / base_10 * 100
        else:
            pct_10 = 0
        return {
            'vol': last_row['成交量'], 'pct_10': round(pct_10, 2),
            'price': current_price,
            'open_pct': round((last_row['开盘'] - prev_row['收盘']) / prev_row['收盘'] * 100, 2),
            'today_pct': round(last_row['涨跌幅'], 2),
            'high': last_row['最高'], 'low': last_row['最低'],
            'prev_close': prev_row['收盘']
        }
    except:
        return None


def check_special_shape(m_data):
    tags = []
    if m_data:
        low_pct = (m_data['low'] - m_data['prev_close']) / m_data['prev_close'] * 100
        if low_pct < -9.0 and m_data['today_pct'] > 9.0: tags.append("🔥地天板")
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

            # 取成交额前2
            df = df.sort_values(by='成交额', ascending=False).head(2)

            for _, row in df.iterrows():
                code, name = row['代码'], row['名称']
                tag_suffix = f"/{concept}中军"

                # 🛠️ 修改点：如果已存在，则追加标签
                if code in seen_codes:
                    for item in strategy_rows:
                        if item['code'] == code:
                            # 避免重复添加相同的标签
                            if tag_suffix not in item['tag']:
                                item['tag'] += tag_suffix
                                print(f"追加标签: {name} -> {item['tag']}")
                    continue  # 处理完追加后，跳过新增逻辑

                # 如果不存在，则新增
                m_data = get_market_data(code)
                if m_data:
                    final_tag = f"{concept}中军"  # 初始标签
                    strategy_rows.append({
                        'code': code, 'name': name, 'tag': final_tag,
                        'link_dragon': get_link_dragon(code),
                        'vol': m_data['vol'], 'pct_10': m_data['pct_10'],
                        'price': m_data['price'], 'open_pct': m_data['open_pct'],
                        'today_pct': m_data['today_pct']
                    })
                    seen_codes.add(code)
                    print(f"入池: {name} ({final_tag})")
            time.sleep(0.5)
        except Exception as e:
            # 建议打印错误，防止API悄悄失败
            print(f"⚠️ 板块 {concept} 获取失败: {e}")
            pass

def generate_csv():
    # 1. 确定日期
    date_str = get_target_date_str()
    print(f"{Fore.CYAN}⏳ 启动复盘生成 | 目标日期: {date_str} ...{Fore.RESET}")

    strategy_rows = []
    seen_codes = set()

    # 2. 读取各类文件
    my_holdings = parse_holdings_text()
    my_ths_list = parse_ths_clipboard()

    # 3. 合并列表 (持仓 > F佬 > 同花顺)
    combined_manual_list = my_ths_list.copy()
    combined_manual_list.update(F_LAO_LIST)
    combined_manual_list.update(my_holdings)

    def add_item(code, name, base_tag):
        if code in seen_codes: return
        m_data = get_market_data(code)
        if m_data:
            special_tags = check_special_shape(m_data)
            final_tag = f"{base_tag}/🔥地天板" if "🔥地天板" in special_tags else base_tag
            strategy_rows.append({
                'code': code, 'name': name, 'tag': final_tag,
                'link_dragon': get_link_dragon(code),
                'vol': m_data['vol'], 'pct_10': m_data['pct_10'],
                'price': m_data['price'], 'open_pct': m_data['open_pct'],
                'today_pct': m_data['today_pct']
            })
            seen_codes.add(code)
            print(f"入池: {name:<8} ({final_tag})")

    # --- 扫描流程 ---
    print(f"\n{Fore.YELLOW}[1/5] 抓取涨停数据 ({date_str})...{Fore.RESET}")
    try:
        # 注意：这里使用的是 date_str，可以抓取历史涨停板
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                open_num = row['炸板次数']
                is_first_limit = row['首次封板时间'] == row['最后封板时间']
                tag = f"{row['连板数']}板"
                if open_num > 0:
                    tag += f"/回封(炸{open_num}次)"
                elif is_first_limit:
                    tag += "/硬板(无炸)"
                else:
                    tag += "/强势"
                add_item(row['代码'], row['名称'], tag)
        else:
            print(f"{Fore.RED}⚠️ 未获取到 {date_str} 的涨停数据 (可能是休市或数据未更新){Fore.RESET}")
    except Exception as e:
        print(f"获取涨停数据失败: {e}")

    print(f"\n{Fore.YELLOW}[2/5] 抓取炸板数据 ({date_str})...{Fore.RESET}")
    try:
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if not df_zb.empty:
            for _, row in df_zb.iterrows(): add_item(row['代码'], row['名称'], "炸板/反包预期")
    except:
        pass

    print(f"\n{Fore.YELLOW}[3/5] 抓取跌停数据 ({date_str})...{Fore.RESET}")
    try:
        df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        if not df_dt.empty:
            for _, row in df_dt.iterrows(): add_item(row['代码'], row['名称'], "跌停/博弈修复")
    except:
        pass

    print(f"\n{Fore.YELLOW}[4/5] 挖掘板块中军 (实时)...{Fore.RESET}")
    add_sector_leaders(strategy_rows, seen_codes)

    print(f"\n{Fore.YELLOW}[5/5] 注入持仓与关注...{Fore.RESET}")
    for code, tag in combined_manual_list.items():
        if code in seen_codes:
            for item in strategy_rows:
                if item['code'] == code:
                    orig_parts = item['tag'].split('/')
                    board_info = orig_parts[0] if '板' in orig_parts[0] else ''
                    status_info = ""
                    for part in orig_parts:
                        if "回封" in part or "硬板" in part or "强势" in part:
                            status_info = part
                            break
                    new_tag = tag
                    if board_info: new_tag = f"{board_info}/{tag}"
                    if status_info: new_tag += f"/{status_info}"
                    item['tag'] = new_tag
                    item['link_dragon'] = get_link_dragon(code)
                    break
        else:
            try:
                if "同花顺/" in tag:
                    name_guess = tag.split('/')[1]
                else:
                    name_guess = tag.split('/')[1].split('(')[0] if '/' in tag else "关注股"
                add_item(code, name_guess, tag)
            except:
                add_item(code, "关注标的", tag)

    if strategy_rows:
        df_save = pd.DataFrame(strategy_rows)
        df_save['sina_code'] = df_save['code'].apply(format_sina)
        cols = ['sina_code', 'name', 'tag', 'today_pct', 'open_pct', 'price', 'pct_10', 'link_dragon', 'vol', 'code']
        df_save = df_save.reindex(columns=cols)
        df_save.sort_values(by=['tag'], ascending=False, inplace=True)

        # 📂 保存逻辑升级
        # 1. 保存带日期的存档文件
        filename_dated = f'strategy_pool_{date_str}.csv'
        df_save.to_csv(filename_dated, index=False, encoding='utf-8-sig')
        print(f"\n✅ 历史存档已生成: {filename_dated} ({len(df_save)} 只)")

        # 2. 复制一份为 strategy_pool.csv (供 monitor_bid.py 默认读取)
        # 只有当生成的是“今天”的数据，或者你强制想让监控看某天的数据时
        shutil.copyfile(filename_dated, 'strategy_pool.csv')
        print(f"✅ 监控链接已更新: strategy_pool.csv -> {filename_dated}")


if __name__ == "__main__":
    generate_csv()