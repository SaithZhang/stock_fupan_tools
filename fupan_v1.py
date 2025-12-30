import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from tabulate import tabulate
import time

# 初始化颜色
init(autoreset=True)

# ================= 配置区 =================
CONFIG = {
    'limit_10': 1.0,  # 10日涨幅偏离值阈值 (100%)
    'limit_30': 2.0,  # 30日涨幅偏离值阈值 (200%)
    'show_first_board': True  # 是否显示首板
}


# =========================================

def get_latest_trading_date():
    now = datetime.now()
    # 简单逻辑：如果当前时间早于9点，大概率是看前一天的复盘，取昨天；否则取今天
    # 实际请求时akshare会自动处理，这里取当天日期即可
    return now.strftime("%Y%m%d")


def get_limit_up_pool():
    """获取涨停池并清洗数据"""
    date_str = get_latest_trading_date()
    print(f"{Fore.CYAN}⏳ [Bo佬复盘] 正在拉取同花顺涨停数据 ({date_str})...{Style.RESET_ALL}")

    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        return df_zt, df_zb
    except Exception as e:
        print(f"{Fore.RED}数据拉取失败，请检查网络或日期: {e}{Style.RESET_ALL}")
        return pd.DataFrame(), pd.DataFrame()


def analyze_regulatory_space(code, current_price, name):
    """
    F哥核心算法：异动空间计算器
    计算距离100%和200%监管线还剩多少涨幅空间
    """
    try:
        # 拉取K线数据 (取足够长以计算30日)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")

        # 必须用后复权或不复权计算真实价格波动？监管通常看实际波动，这里用前复权近似模拟
        df_hist = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date,
                                     adjust="qfq")

        if df_hist.empty or len(df_hist) < 30:
            return {'10日%': 0, '30日%': 0, '10日余量': 999, '30日余量': 999, '提示': '次新/数据少'}

        # 获取基准收盘价
        # 监管规则通常是：(T日收盘价 - T-10日收盘价) / T-10日收盘价
        # 注意：这里取倒数第11天的数据作为基准(T-10的对比基准)
        def get_pct_and_space(days_ago, limit_threshold):
            if len(df_hist) <= days_ago: return 0, 999

            base_price = df_hist.iloc[-(days_ago + 1)]['收盘']  # T-N日的基准价
            current_pct = (current_price - base_price) / base_price

            # 计算触发监管的价格
            trigger_price = base_price * (1 + limit_threshold)
            # 计算距离触发价格还有多少个百分点 (Current -> Trigger)
            # 空间 = (触发价 - 现价) / 现价
            space_pct = (trigger_price - current_price) / current_price

            return current_pct, space_pct

        pct_10, space_10 = get_pct_and_space(10, CONFIG['limit_10'])
        pct_30, space_30 = get_pct_and_space(30, CONFIG['limit_30'])

        # 构造提示语
        tags = []

        # 10日线逻辑
        p10_str = f"{pct_10 * 100:.0f}%"
        if pct_10 > CONFIG['limit_10']:
            tags.append(f"{Fore.RED}已破10日线{Style.RESET_ALL}")
        elif space_10 < 0.1:  # 离异动不到10%（约1个板）
            tags.append(f"{Fore.YELLOW}10日压线(余{space_10 * 100:.1f}%){Style.RESET_ALL}")
        else:
            tags.append(f"{Fore.GREEN}10日安全{Style.RESET_ALL}")

        # 30日线逻辑
        p30_str = f"{pct_30 * 100:.0f}%"
        if pct_30 > CONFIG['limit_30']:
            tags.append(f"{Fore.MAGENTA}已破30日线{Style.RESET_ALL}")
        elif space_30 < 0.1:
            tags.append(f"{Fore.YELLOW}30日压线(余{space_30 * 100:.1f}%){Style.RESET_ALL}")

        return {
            '10日%': p10_str,
            '30日%': p30_str,
            '10日余量': space_10,  # 浮点数方便排序或判断
            '30日余量': space_30,
            '提示': " ".join(tags)
        }

    except Exception as e:
        return {'10日%': '-', '30日%': '-', '提示': '计算错'}


def analyze_ladder():
    df_zt, df_zb = get_limit_up_pool()
    if df_zt.empty: return

    # ================= 情绪概览 =================
    zt_count = len(df_zt)
    zb_count = len(df_zb)
    total = zt_count + zb_count
    success_rate = zt_count / total * 100 if total > 0 else 0

    print("\n" + "=" * 80)
    print(f"📊 {Fore.YELLOW}Bo佬 & F哥 联合复盘看板{Style.RESET_ALL} | {get_latest_trading_date()}")
    print(
        f"全市场涨停: {Fore.RED}{zt_count}{Style.RESET_ALL} | 炸板: {Fore.GREEN}{zb_count}{Style.RESET_ALL} | 封板率: {success_rate:.1f}%")
    print(f"核心策略: {Fore.CYAN}弱转强(关注烂板/爆量) | 控异动(关注余量) | 卡位分离{Style.RESET_ALL}")
    print("=" * 80)

    # ================= 数据清洗 =================
    col_lbc = '连板数' if '连板数' in df_zt.columns else 'lbc'
    df_zt['lbc_int'] = df_zt[col_lbc].astype(int)

    # 梯队划分
    ladders = {
        '👑 核心高标 (4板+)': df_zt[df_zt['lbc_int'] >= 4],
        '⚔️ 渡劫/争夺 (3板)': df_zt[df_zt['lbc_int'] == 3],
        '🔥 晋级确认 (2板)': df_zt[df_zt['lbc_int'] == 2],
        '🌱 首板挖掘 (1板)': df_zt[df_zt['lbc_int'] == 1]
    }

    for title, sub_df in ladders.items():
        if sub_df.empty: continue
        if '首板' in title and not CONFIG['show_first_board']:
            print(f"\n{title}: {len(sub_df)} 只 (已折叠)")
            continue

        print(f"\n{Fore.WHITE}【{title}】{Style.RESET_ALL}")

        # 准备表格数据
        table_data = []
        # 按封板时间排序，越早封板越强，越晚封板越可能是烂板/弱转强预期
        if '最后封板时间' in sub_df.columns:
            sub_df = sub_df.sort_values(by='最后封板时间')

        for _, row in sub_df.iterrows():
            code = row['代码']
            name = row['名称']
            price = row['最新价']
            lbc = row['lbc_int']
            reason = row.get('涨停原因类别', row.get('所属行业', '未知'))
            # 截取板块前几个字，避免太长
            reason = reason[:8] if isinstance(reason, str) else str(reason)

            # 时间处理
            time_last = str(row.get('最后封板时间', '-'))

            # 资金处理
            money = row.get('封板资金', 0)
            money_str = f"{int(money / 10000)}万"

            # 换手率高亮：F哥关注大分歧，换手高可能是弱转强前兆
            turnover = row['换手率']
            turnover_str = f"{turnover:.1f}%"
            if turnover > 15:
                turnover_str = f"{Fore.YELLOW}{turnover_str}{Style.RESET_ALL}"

            # 监管计算 (仅针对2板及以上，或者特定辨识度首板)
            reg_status = ""
            reg_p10 = "-"
            reg_p30 = "-"

            if lbc >= 2:
                # 打印进度避免假死
                print(f"\r🔍 计算异动: {name}...", end="")
                res = analyze_regulatory_space(code, price, name)
                reg_p10 = res['10日%']
                reg_p30 = res['30日%']
                reg_status = res['提示']

            # 名称染色逻辑
            name_display = name
            if "压线" in reg_status:
                # 控异动标的，高亮显示（F哥重点：鹭燕模式）
                name_display = f"{Fore.CYAN}{name}{Style.RESET_ALL}"
            elif "已破" in reg_status:
                # 严重异动，风险标的（F哥重点：神剑模式）
                name_display = f"{Fore.RED}{name}{Style.RESET_ALL}"

            # 弱转强标识：如果是烂板（下午14:30后封板）
            is_weak = False
            if len(time_last) == 6 and int(time_last) > 143000:
                time_last = f"{Fore.MAGENTA}{time_last}(烂){Style.RESET_ALL}"
                is_weak = True

            # 构造行
            table_data.append([
                name_display,
                price,
                f"{lbc}板",
                reason,
                time_last,
                turnover_str,
                money_str,
                reg_p10,
                reg_p30,
                reg_status
            ])

        print("\r" + " " * 30 + "\r", end="")  # 清行
        headers = ["名称", "价格", "高度", "板块/原因", "最后封板", "换手", "封单", "10日涨", "30日涨", "异动监管判定"]
        print(tabulate(table_data, headers=headers, tablefmt="simple"))

    print("\n" + "=" * 80)
    print(f"{Fore.CYAN}💡 竞价关注逻辑 (F哥思路):{Style.RESET_ALL}")
    print("1. 寻找【监管安全】且【板块有逻辑】的个股 (如: 航天+未破100%)")
    print("2. 关注【烂板/高换手】个股明日竞价是否超预期 (弱转强)")
    print("3. 警惕【红色名字】个股的回调风险 (严重异动)")
    print("=" * 80)


if __name__ == "__main__":
    analyze_ladder()