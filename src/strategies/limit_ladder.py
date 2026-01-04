import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from tabulate import tabulate
import time

# 初始化颜色
init(autoreset=True)

# =================配置区=================
CONFIG = {
    'risk_limit_10': 0.95,  # 10日涨幅预警 (95%高危)
    'risk_limit_30': 1.95,  # 30日涨幅预警
    'show_first_board': False  # 是否显示首板 (复盘通常只看连板，True可开启)
}


# =======================================

def get_latest_trading_date():
    """获取最近的一个交易日"""
    now = datetime.now()
    # 简单处理：如果是下午3点后，取今天；否则取今天（akshare会自动处理非交易日返回空或报错，我们尽量传今天日期）
    return now.strftime("%Y%m%d")


def get_limit_up_pool():
    """获取今日涨停池 + 炸板池"""
    date_str = get_latest_trading_date()
    print(f"{Fore.CYAN}⏳ 正在拉取同花顺涨停梯队数据 ({date_str})...{Style.RESET_ALL}")

    try:
        # 1. 涨停池
        df_zt = ak.stock_zt_pool_em(date=date_str)
        # 2. 炸板池 (计算情绪用)
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)

        return df_zt, df_zb
    except Exception as e:
        print(f"{Fore.RED}数据拉取失败: {e}{Style.RESET_ALL}")
        return pd.DataFrame(), pd.DataFrame()


def calculate_regulatory_risk(code, current_price):
    """
    F佬监管计算器：计算5日、10日、30日涨幅
    只对连板股调用，减少请求次数
    """
    try:
        # 拉取最近40天数据
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")

        df_hist = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date,
                                     adjust="qfq")

        if df_hist.empty or len(df_hist) < 30:
            return None

        # 定义计算涨幅的函数
        def get_pct(days_ago):
            # 确保历史数据足够
            if len(df_hist) < days_ago + 1: return 0
            # 倒数第N+1行作为基准 (T-N)
            base_price = df_hist.iloc[-(days_ago + 1)]['收盘']
            return (current_price - base_price) / base_price

        pct_5 = get_pct(5)
        pct_10 = get_pct(10)
        pct_30 = get_pct(30)

        # 判定状态
        status = f"{Fore.GREEN}安全{Style.RESET_ALL}"

        if pct_10 > CONFIG['risk_limit_10']:
            status = f"{Fore.RED}⚠️10日异动({pct_10 * 100:.1f}%){Style.RESET_ALL}"
        elif pct_30 > CONFIG['risk_limit_30']:
            status = f"{Fore.MAGENTA}⚠️30日异动({pct_30 * 100:.1f}%){Style.RESET_ALL}"
        elif pct_10 > 0.8:
            status = f"{Fore.YELLOW}⚡接近监管({pct_10 * 100:.1f}%){Style.RESET_ALL}"

        return {
            '10日%': round(pct_10 * 100, 1),
            '30日%': round(pct_30 * 100, 1),
            '监管状态': status
        }

    except:
        return {'10日%': '-', '30日%': '-', '监管状态': '---'}


def analyze_ladder():
    df_zt, df_zb = get_limit_up_pool()

    if df_zt.empty:
        print("今日无涨停数据 (可能是非交易日或数据尚未更新)。")
        return

    # ---------------- 情绪概览 ----------------
    print("\n" + "=" * 60)
    zt_count = len(df_zt)
    zb_count = len(df_zb)
    success_rate = zt_count / (zt_count + zb_count) * 100 if (zt_count + zb_count) > 0 else 0

    print(f"📊 {Fore.YELLOW}Bo佬情绪面板{Style.RESET_ALL}")
    print(f"涨停家数: {Fore.RED}{zt_count}{Style.RESET_ALL} 家 | 炸板家数: {Fore.GREEN}{zb_count}{Style.RESET_ALL} 家")
    print(f"封板成功率: {Fore.CYAN}{success_rate:.1f}%{Style.RESET_ALL} (低于70%需退潮防守)")

    # ---------------- 梯队划分 ----------------
    # 确保列名正确，防止报错
    col_lbc = '连板数' if '连板数' in df_zt.columns else 'lbc'  # 防御性编程

    df_zt['lbc_int'] = df_zt[col_lbc].astype(int)

    # 定义梯队
    ladders = {
        '👑 妖股/高标 (4板以上)': df_zt[df_zt['lbc_int'] >= 4],
        '🚀 3连板 (渡劫期)': df_zt[df_zt['lbc_int'] == 3],
        '🔥 2连板 (晋级确认)': df_zt[df_zt['lbc_int'] == 2],
        '🌱 首板 (挖掘/套利)': df_zt[df_zt['lbc_int'] == 1]
    }

    print("=" * 60)

    for title, sub_df in ladders.items():
        if sub_df.empty: continue
        if title == '🌱 首板 (挖掘/套利)' and not CONFIG['show_first_board']:
            print(f"\n{title}: 共 {len(sub_df)} 只 (已隐藏，配置可开启)")
            continue

        print(f"\n{Fore.WHITE}【{title}】 共 {len(sub_df)} 只{Style.RESET_ALL}")

        table_data = []
        # 按最后封板时间排序
        if '最后封板时间' in sub_df.columns:
            sub_df = sub_df.sort_values(by='最后封板时间')

        for _, row in sub_df.iterrows():
            code = row['代码']
            name = row['名称']
            price = row['最新价']
            lbc = row['lbc_int']
            turnover = row['换手率']

            # 兼容字段名: 最后封板时间 / 首次封板时间
            time_last = row.get('最后封板时间', str(row.get('首次封板时间', '-')))

            # 修复字段名: 封板资金
            money = row.get('封板资金', 0)

            # 格式化封单额 (亿/万)
            if money > 100000000:
                money_str = f"{money / 100000000:.2f}亿"
            else:
                money_str = f"{money / 10000:.0f}万"

            # 监管计算 (2板及以上)
            reg_info = {'10日%': '-', '30日%': '-', '监管状态': '---'}
            if lbc >= 2:
                print(f"\r正在扫描监管数据: {name}...", end="")
                calc = calculate_regulatory_risk(code, price)
                if calc: reg_info = calc

            # 名称高亮
            name_display = name
            if "⚠️" in str(reg_info['监管状态']):
                name_display = f"{Fore.RED}{name}{Style.RESET_ALL}"

            table_data.append([
                name_display,
                price,
                f"{Fore.YELLOW}{lbc}板{Style.RESET_ALL}",
                time_last,
                f"{turnover:.1f}%",
                money_str,
                reg_info['10日%'],
                reg_info['30日%'],
                reg_info['监管状态']
            ])

        print("\r" + " " * 40 + "\r", end="")  # 清除进度条

        headers = ["名称", "现价", "高度", "封板", "换手", "封单", "10日涨", "30日涨", "F佬监管判定"]
        print(tabulate(table_data, headers=headers, tablefmt="simple"))


if __name__ == "__main__":
    analyze_ladder()