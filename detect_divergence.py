# ==============================================================================
# 📌 4. F佬/Bo佬 逆势猎手 (detect_divergence.py) - 寻找抗跌真龙
# ==============================================================================
# 核心逻辑：
# 1. 获取"航天发展"今天的分钟级数据，找到跌势最凶的时段。
# 2. 遍历策略池，计算同一时段内其他个股的涨跌幅。
# 3. 筛选出"中军大跌、小弟大涨"的逆势品种。
# ==============================================================================

import akshare as ak
import pandas as pd
import time
from colorama import init, Fore, Style

init(autoreset=True)

# 🎯 核心锚点：航天发展 (跳水的中军)
ANCHOR_CODE = "000547"
ANCHOR_NAME = "航天发展"

# 策略池路径
CSV_PATH = 'strategy_pool.csv'


def get_minute_data(symbol):
    """获取今日分钟级数据"""
    try:
        # akshare 分钟数据接口
        df = ak.stock_zh_a_hist_min_em(symbol=symbol, period='1', adjust='qfq')
        # 只要今天的 (假设最后一行是今天的)
        today_date = df.iloc[-1]['时间'].split(' ')[0]
        df = df[df['时间'].str.contains(today_date)]
        return df
    except:
        return None


def find_diving_window(df_anchor):
    """
    找到锚定股票跳水最猛的时段 (这里简化为取最后30分钟，响应F佬说的'尾盘跳水')
    或者你可以写算法找跌幅最大的区间
    """
    # F佬复盘提到"尾盘跳水"，我们取 14:30 - 15:00
    # 格式转换
    df_anchor['time_str'] = df_anchor['时间'].apply(lambda x: x.split(' ')[1])

    # 截取尾盘数据
    start_time = "14:30:00"
    end_time = "15:00:00"

    mask = (df_anchor['time_str'] >= start_time) & (df_anchor['time_str'] <= end_time)
    df_window = df_anchor.loc[mask]

    if df_window.empty: return None, 0

    # 计算区间跌幅
    start_price = df_window.iloc[0]['开盘']
    end_price = df_window.iloc[-1]['收盘']
    pct = (end_price - start_price) / start_price * 100

    return mask, pct


def main():
    print(f"{Fore.CYAN}🕵️‍♂️ 正在启动逆势猎手，分析锚点：{ANCHOR_NAME} ({ANCHOR_CODE})...{Style.RESET_ALL}")

    # 1. 获取锚点数据
    df_anchor = get_minute_data(ANCHOR_CODE)
    if df_anchor is None:
        print("无法获取锚点数据")
        return

    # 2. 确定跳水区间
    time_mask, anchor_pct = find_diving_window(df_anchor)
    print(f"📉 {ANCHOR_NAME} 尾盘(14:30-15:00) 表现: {Fore.GREEN}{anchor_pct:.2f}%{Style.RESET_ALL}")

    if anchor_pct > 0:
        print("提示：锚点尾盘是涨的？可能找错参照物了，或者今天没跳水。")

    # 3. 加载策略池
    try:
        pool_df = pd.read_csv(CSV_PATH)
    except:
        print("找不到 strategy_pool.csv")
        return

    print(f"\n🚀 开始全池扫描 ({len(pool_df)}只)，寻找逆势英雄...\n")
    print(f"{'代码':<8} {'名称':<8} {'尾盘涨幅(逆势)':<14} {'全天涨幅':<10} {'评价'}")
    print("-" * 60)

    heroes = []

    for _, row in pool_df.iterrows():
        code = row['code']
        name = row['name']

        # 跳过锚点自己
        if code == ANCHOR_CODE: continue

        # 获取分钟数据
        df_target = get_minute_data(str(code))
        if df_target is None or df_target.empty: continue

        # 格式化时间以匹配 mask
        df_target['time_str'] = df_target['时间'].apply(lambda x: x.split(' ')[1])

        # 提取同时段数据
        # 注意：这里需要重新通过时间筛选，因为不同股票数据行数可能不一致
        start_time = "14:30:00"
        end_time = "15:00:00"
        mask = (df_target['time_str'] >= start_time) & (df_target['time_str'] <= end_time)
        df_win = df_target.loc[mask]

        if df_win.empty: continue

        # 计算该股在同一时间段的表现
        t_start = df_win.iloc[0]['开盘']
        t_end = df_win.iloc[-1]['收盘']
        t_pct = (t_end - t_start) / t_start * 100

        # 筛选逻辑：航天发展跌，它却涨，或者特别抗跌(>-0.5%)
        if t_pct > 0:
            tag = f"{Fore.RED}🔥逆势拉升{Style.RESET_ALL}"
            heroes.append(
                {'code': code, 'name': name, 'div_pct': t_pct, 'day_pct': row.get('today_pct', 0), 'tag': tag})
            # 实时打印
            print(
                f"{code:<8} {name:<8} {Fore.RED}+{t_pct:.2f}%{Style.RESET_ALL}        {row.get('today_pct', 0):<10} {tag}")

        elif t_pct > anchor_pct + 2.0:  # 比大哥少跌很多也算强
            tag = f"{Fore.YELLOW}🛡️抗跌{Style.RESET_ALL}"
            # 这一行可以选择性打印，避免刷屏
            # print(f"{code:<8} {name:<8} {t_pct:.2f}%          {row.get('today_pct', 0):<10} {tag}")

    print("-" * 60)
    print(f"\n🏆 扫描完成，共发现 {len(heroes)} 位逆势英雄。")
    print("👉 重点关注这些票明天的竞价，如果红开，高看一眼！")


if __name__ == "__main__":
    main()