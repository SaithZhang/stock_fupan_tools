# ==============================================================================
# 📌 1. F佬/Bo佬 离线复盘生成器 (fupan_generator.py) - 中军增强版
# ==============================================================================
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import os
import time
import sys
from colorama import init, Fore

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 配置区 =================

# 1. 定义当前市场的核心热点板块 (脚本会自动去抓这些板块的大屁股中军)
# 注意：名称必须准确匹配东方财富的板块名称
# 格式: (板块名称, 板块类型) 其中类型: 'concept'=概念板块, 'industry'=行业板块
HOT_CONCEPTS = [
    ('人形机器人', 'concept'),
    ('商业航天', 'concept'),
    ('消费电子', 'industry'),  # 消费电子是行业板块，不是概念板块
    ('低空经济', 'concept'),
    ('苹果概念', 'concept'),
    ('华为概念', 'concept')
]

# 2. 手动录入关注标的 (F佬点名 + 你的持仓)
MANUAL_LIST = {
    # --- F佬/Bo佬 核心点名 ---
    '002788': 'F佬/鹭燕(控异动)',
    '000547': 'F佬/航发(0.2%空间)',
    '002682': 'F佬/龙洲(出监管)',
    '000592': 'F佬/平潭(尾盘抢筹)',
    '600118': 'F佬/卫星(弱转强)',
    '600693': 'F佬/东百(跌停风向)',

    # --- 你的持仓 ---
    '603667': '持仓/五洲(机器人/航天)',
    '002703': '持仓/世宝(自动驾驶)',
    '300115': '持仓/长盈(消电中军)',
    '600592': '持仓/龙溪(航天/机器人)',
    '001231': '持仓/农心(农业)',
    '300223': '持仓/君正(存储)',
    '600755': '持仓/国贸(博弈修复)',
}

# 3. 强弱联动映射表
LINK_DRAGON_MAP = {
    '600592': '603667',  # 龙溪 -> 五洲
    '300115': '002475',  # 长盈 -> 立讯精密(sz002475)
}


# ========================================================================

def format_sina(code):
    code = str(code)
    if code.startswith('6'): return f"sh{code}"
    if code.startswith('8') or code.startswith('4'): return f"bj{code}"
    return f"sz{code}"


def get_link_dragon(code):
    dragon = LINK_DRAGON_MAP.get(code, '')
    if dragon: return format_sina(dragon)
    return ''


def get_market_data(code):
    try:
        # 获取近30天数据
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df.empty or len(df) < 15: return None

        last_row = df.iloc[-1]
        yesterday_vol = last_row['成交量']
        current_price = last_row['收盘']

        # 简单计算10日涨幅
        if len(df) > 11:
            base_10 = df.iloc[-11]['收盘']
            pct_10 = (current_price - base_10) / base_10 * 100
        else:
            pct_10 = 0

        return {'vol': yesterday_vol, 'pct_10': round(pct_10, 2), 'price': current_price}
    except:
        return None


def add_sector_leaders(strategy_rows, seen_codes):
    """
    [新增功能] 自动抓取热点板块的中军（成交额前2名）
    """
    print(f"\n{Fore.MAGENTA}🔎 正在挖掘板块中军 (成交额Top2)...{Fore.RESET}")

    for concept_info in HOT_CONCEPTS:
        # 支持新格式 (名称, 类型) 和旧格式 (仅名称，默认为概念板块)
        if isinstance(concept_info, tuple):
            concept, board_type = concept_info
        else:
            concept = concept_info
            board_type = 'concept'  # 默认使用概念板块

        try:
            # 根据板块类型选择不同的API
            if board_type == 'industry':
                df = ak.stock_board_industry_cons_em(symbol=concept)
            else:
                df = ak.stock_board_concept_cons_em(symbol=concept)

            # 检查DataFrame是否为空
            if df is None or df.empty:
                print(f"⚠️  {concept} 板块数据为空，跳过")
                continue

            # 检查是否有'成交额'列
            if '成交额' not in df.columns:
                print(f"⚠️  {concept} 板块数据缺少'成交额'列，跳过")
                continue

            # 按成交额降序排序 (大资金都在这就对了)
            df = df.sort_values(by='成交额', ascending=False)

            # 取前2名作为中军
            top_2 = df.head(2)

            if top_2.empty:
                print(f"⚠️  {concept} 板块无有效股票，跳过")
                continue

            for _, row in top_2.iterrows():
                code = row['代码']
                name = row['名称']

                if code in seen_codes: continue

                # 获取数据
                m_data = get_market_data(code)
                if m_data:
                    strategy_rows.append({
                        'code': code,
                        'name': name,
                        'tag': f"{concept}中军",  # 自动打标
                        'link_dragon': get_link_dragon(code),
                        'vol': m_data['vol'],
                        'pct_10': m_data['pct_10'],
                        'price': m_data['price']
                    })
                    seen_codes.add(code)
                    print(f"入池: {name} ({concept}中军) - 成交额霸主")

            time.sleep(0.5)  # 防止请求过快
        except Exception as e:
            print(f"⚠️  获取 {concept} 失败: {e}")


def generate_csv():
    print(f"{Fore.CYAN}⏳ 正在启动全市场扫描...{Fore.RESET}")
    date_str = datetime.now().strftime("%Y%m%d")
    strategy_rows = []
    seen_codes = set()

    # 辅助添加函数
    def add_item(code, name, tag):
        if code in seen_codes: return
        m_data = get_market_data(code)
        if m_data:
            strategy_rows.append({
                'code': code, 'name': name, 'tag': tag,
                'link_dragon': get_link_dragon(code),
                **m_data
            })
            seen_codes.add(code)
            print(f"{Fore.GREEN}入池: {name:<8} ({tag}){Fore.RESET}")

    # 1. 涨停
    print(f"\n{Fore.YELLOW}[1/5] 抓取涨停...{Fore.RESET}")
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if not df_zt.empty:
            for _, row in df_zt.iterrows():
                last_time = str(row['最后封板时间'])
                tag = f"{row['连板数']}板/强势"
                if len(last_time) >= 5 and int(last_time) > 143000:
                    tag = f"{row['连板数']}板/烂板(弱转强)"
                add_item(row['代码'], row['名称'], tag)
    except:
        pass

    # 2. 炸板
    print(f"\n{Fore.YELLOW}[2/5] 抓取炸板...{Fore.RESET}")
    try:
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if not df_zb.empty:
            for _, row in df_zb.iterrows():
                add_item(row['代码'], row['名称'], "炸板/反包预期")
    except:
        pass

    # 3. 跌停
    print(f"\n{Fore.YELLOW}[3/5] 抓取跌停...{Fore.RESET}")
    try:
        df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
        if not df_dt.empty:
            for _, row in df_dt.iterrows():
                add_item(row['代码'], row['名称'], "跌停/博弈修复")
    except:
        pass

    # 4. [新] 自动挖掘中军
    print(f"\n{Fore.YELLOW}[4/5] 挖掘板块中军...{Fore.RESET}")
    add_sector_leaders(strategy_rows, seen_codes)

    # 5. 手动配置
    print(f"\n{Fore.YELLOW}[5/5] 注入持仓/自选...{Fore.RESET}")
    for code, tag in MANUAL_LIST.items():
        if code in seen_codes:
            for item in strategy_rows:
                if item['code'] == code:
                    item['tag'] = tag  # 优先用手动Tag覆盖
                    break
        else:
            add_item(code, "自选标的", tag)

    # 保存
    if strategy_rows:
        df_save = pd.DataFrame(strategy_rows)
        df_save['sina_code'] = df_save['code'].apply(format_sina)
        cols = ['sina_code', 'name', 'tag', 'vol', 'pct_10', 'link_dragon', 'price', 'code']
        df_save = df_save.reindex(columns=cols)
        df_save.to_csv('strategy_pool.csv', index=False, encoding='utf-8-sig')
        print(f"\n✅ 策略池已生成: {len(df_save)} 只标的")


if __name__ == "__main__":
    generate_csv()