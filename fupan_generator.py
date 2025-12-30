# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (fupan_generator.py) - 银河持仓直读版
# ==============================================================================
# 更新日志：
# 1. [持仓读取] 支持直接解析银河证券复制的文本(holdings.txt)。
# 2. [自动过滤] 自动剔除股票余额为0的清仓股。
# 3. [策略映射] 根据 HOLDING_STRATEGIES 字典自动给持仓股打上策略标签。
# ==============================================================================

import akshare as ak
import pandas as pd
from datetime import datetime
import os
import time
import sys
import re  # 正则表达式用于解析文本
from colorama import init, Fore

if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 配置区 =================

# 1. 核心热点板块
HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('AI智能体', 'concept'),
    ('消费电子概念', 'concept'),
    ('低空经济', 'concept'),
]

# 2. [固定] F佬/Bo佬 核心关注
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

# 3. [新增] 持仓股的策略映射表 (代码 : (标签, 大哥代码))
# 作用：当脚本从 holdings.txt 读到这些代码时，自动应用这里的策略
HOLDING_STRATEGIES = {
    '603667': ('持仓/五洲(机器人/航天)', ''),
    '300115': ('持仓/长盈(消电中军)', 'sz002475'),  # 绑定立讯
    '300223': ('持仓/君正(存储)', ''),
    '001231': ('持仓/农心(农业)', ''),
    '002703': ('持仓/世宝(需红开)', ''),
    '600755': ('持仓/国贸(博弈修复)', ''),
    # 如果买了新票这里没配，默认会显示 "持仓/观察"
}

# 4. 默认的大哥联动 (非持仓股的通用联动)
LINK_DRAGON_MAP = {
    '002009': '002931',  # 天奇 -> 锋龙
}


# ========================================================================

def format_sina(code):
    code = str(code)
    if code.startswith('6'): return f"sh{code}"
    if code.startswith('8') or code.startswith('4'): return f"bj{code}"
    return f"sz{code}"


def get_link_dragon(code):
    # 先查持仓策略表
    if code in HOLDING_STRATEGIES:
        dragon = HOLDING_STRATEGIES[code][1]
        if dragon: return dragon

    # 再查通用表
    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon:
        if dragon.startswith('sz') or dragon.startswith('sh'): return dragon
        return format_sina(dragon)
    return ''


def parse_holdings_text():
    """
    [核心] 解析银河证券复制的文本数据
    """
    file_path = 'holdings.txt'
    if not os.path.exists(file_path):
        print(f"{Fore.YELLOW}⚠️ 未找到 {file_path}，跳过持仓加载。{Fore.RESET}")
        return {}

    holdings = {}
    print(f"{Fore.CYAN}📂 正在读取持仓文件: {file_path}{Fore.RESET}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or "证券代码" in line or "合计" in line: continue

            # 使用正则拆分，处理不定长的空格/Tab
            parts = re.split(r'\s+', line)

            if len(parts) < 3: continue

            code = parts[0]
            name = parts[1]
            balance = parts[2]  # 股票余额

            # 过滤掉余额为0的清仓股 (如龙溪)
            try:
                if float(balance) <= 0:
                    continue
            except:
                continue

            # 获取策略配置
            if code in HOLDING_STRATEGIES:
                tag = HOLDING_STRATEGIES[code][0]
                # 大哥逻辑在 get_link_dragon 里处理
            else:
                tag = f"持仓/{name}"  # 默认标签

            holdings[code] = tag

        return holdings

    except Exception as e:
        print(f"{Fore.RED}❌ 解析持仓文件失败: {e}{Fore.RESET}")
        return {}


def get_market_data(code):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df.empty or len(df) < 2: return None

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        current_price = last_row['收盘']
        open_price = last_row['开盘']
        prev_close = prev_row['收盘']
        open_pct = (open_price - prev_close) / prev_close * 100
        today_pct = last_row['涨跌幅']

        if len(df) > 11:
            base_10 = df.iloc[-11]['收盘']
            pct_10 = (current_price - base_10) / base_10 * 100
        else:
            pct_10 = 0

        return {
            'vol': last_row['成交量'], 'pct_10': round(pct_10, 2),
            'price': current_price, 'open_pct': round(open_pct, 2),
            'today_pct': round(today_pct, 2),
            'high': last_row['最高'], 'low': last_row['最低'],
            'prev_close': prev_close
        }
    except:
        return None


def check_special_shape(m_data):
    tags = []
    if m_data:
        low_pct = (m_data['low'] - m_data['prev_close']) / m_data['prev_close'] * 100
        if low_pct < -9.0 and m_data['today_pct'] > 9.0: tags.append("🔥地天板")
        if m_data['open_pct'] > 0:
            tags.append("红开")
        else:
            tags.append("绿开")
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
                if code in seen_codes: continue
                m_data = get_market_data(code)
                if m_data:
                    special_tags = check_special_shape(m_data)
                    tag_str = f"{concept}中军" + ("/地天板" if "🔥地天板" in special_tags else "")
                    strategy_rows.append({
                        'code': code, 'name': name, 'tag': tag_str,
                        'link_dragon': get_link_dragon(code),
                        'vol': m_data['vol'], 'pct_10': m_data['pct_10'],
                        'price': m_data['price'], 'open_pct': m_data['open_pct'],
                        'today_pct': m_data['today_pct']
                    })
                    seen_codes.add(code)
                    print(f"入池: {name} ({tag_str}) 涨幅:{m_data['today_pct']}%")
            time.sleep(0.5)
        except:
            pass


def generate_csv():
    print(f"{Fore.CYAN}⏳ 启动全市场扫描 (银河持仓版)...{Fore.RESET}")
    date_str = datetime.now().strftime("%Y%m%d")
    strategy_rows = []
    seen_codes = set()

    # 1. 自动解析 holdings.txt
    my_holdings = parse_holdings_text()

    # 2. 合并 F佬列表 和 解析出的持仓
    # 优先级：持仓配置 > F佬配置
    combined_manual_list = F_LAO_LIST.copy()
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
            color = Fore.RED if "地天板" in final_tag else Fore.GREEN
            print(f"{color}入池: {name:<8} ({final_tag}) 涨幅:{m_data['today_pct']}%{Fore.RESET}")

    # --- 扫描流程 ---
    # 1. 涨停
    print(f"\n{Fore.YELLOW}[1/5] 抓取涨停...{Fore.RESET}")
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                # 获取关键指标
                open_num = row['炸板次数']  # 炸过几次
                is_first_limit = row['首次封板时间'] == row['最后封板时间']  # 还没炸过

                tag = f"{row['连板数']}板"

                # --- 智能打标逻辑 ---
                if open_num > 0:
                    # 炸过，说明是回封板 (换手板) - 五洲新春属于这种
                    tag += f"/回封(炸{open_num}次)"
                elif is_first_limit:
                    # 没炸过，且首封=尾封，可能是一字或秒板
                    tag += "/硬板(无炸)"
                else:
                    tag += "/强势"

                add_item(row['代码'], row['名称'], tag)
    except:
        pass

    print(f"\n{Fore.YELLOW}[2/5] 抓取炸板...{Fore.RESET}")
    try:
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if not df_zb.empty:
            for _, row in df_zb.iterrows():
                add_item(row['代码'], row['名称'], "炸板/反包预期")
    except:
        pass

    print(f"\n{Fore.YELLOW}[3/5] 抓取跌停...{Fore.RESET}")
    try:
        df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        if not df_dt.empty:
            for _, row in df_dt.iterrows():
                add_item(row['代码'], row['名称'], "跌停/博弈修复")
    except:
        pass

    print(f"\n{Fore.YELLOW}[4/5] 挖掘板块中军...{Fore.RESET}")
    add_sector_leaders(strategy_rows, seen_codes)


    # 找到这段代码 (大概在最后几行)
    print(f"\n{Fore.YELLOW}[5/5] 注入持仓与关注...{Fore.RESET}")
    for code, tag in combined_manual_list.items():
        if code in seen_codes:
            for item in strategy_rows:
                if item['code'] == code:
                    # --- 修改开始 ---
                    # 获取原有的板数和状态信息 (例如: "2板/回封(炸1次)")
                    orig_parts = item['tag'].split('/')

                    # 提取板数 (如 "2板")
                    board_count = orig_parts[0] if '板' in orig_parts[0] else ''

                    # 提取状态 (如 "回封(炸1次)" 或 "硬板(无炸)")
                    # 逻辑：如果tag里有"回封"或"硬板"或"强势"，把它保留下来
                    status = ""
                    for part in orig_parts:
                        if "回封" in part or "硬板" in part or "强势" in part:
                            status = part
                            break

                    # 组合新标签：板数 + 你的逻辑 + 状态
                    # 例如: "2板/持仓/五洲(机器人)/回封(炸1次)"
                    new_tag = tag  # 先用你的逻辑
                    if board_count:
                        new_tag = f"{board_count}/{tag}"
                    if status:
                        new_tag += f"/{status}"

                    item['tag'] = new_tag
                    # --- 修改结束 ---

                    # 强制更新大哥 (持仓逻辑优先)
                    item['link_dragon'] = get_link_dragon(code)
                    break
    # 保存
    if strategy_rows:
        df_save = pd.DataFrame(strategy_rows)
        df_save['sina_code'] = df_save['code'].apply(format_sina)
        cols = ['sina_code', 'name', 'tag', 'today_pct', 'open_pct', 'price', 'pct_10', 'link_dragon', 'vol', 'code']
        df_save = df_save.reindex(columns=cols)
        df_save.sort_values(by=['tag'], ascending=False, inplace=True)

        filename = 'strategy_pool.csv'
        df_save.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 策略池已生成: {filename} ({len(df_save)} 只标的)")


if __name__ == "__main__":
    generate_csv()