import akshare as ak
import numpy as np
import matplotlib.pyplot as plt
import warnings

# 忽略一些pandas的警告
warnings.filterwarnings('ignore')

# ================= 配置区 =================
# 在这里输入你要复盘的股票代码
STOCK_CODE = "600783"
LOOKBACK_DAYS = 120


# =========================================

def get_data(code):
    """获取日线数据并计算基础指标"""
    print(f"正在获取 {code} 行情数据...")
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        df = df.tail(LOOKBACK_DAYS).copy()
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception as e:
        print(f"数据获取失败: {e}")
        return None


def calculate_chip_structure(df):
    """
    【筹码模块】
    计算：平均成本、获利盘比例、乖离率、支撑真空度
    """
    chip_dict = {}  # {价格: 筹码量}

    # 模拟筹码分布
    for index, row in df.iterrows():
        avg_price = (row['最高'] + row['最低'] + row['收盘']) / 3
        turnover = row['换手率'] / 100
        if turnover > 1: turnover = 1

        # 衰减旧筹码
        keys = list(chip_dict.keys())
        for p in keys:
            chip_dict[p] = chip_dict[p] * (1 - turnover)

        # 新增新筹码
        price_key = round(avg_price, 2)
        chip_dict[price_key] = chip_dict.get(price_key, 0) + turnover

    # 统计当前状态
    current_price = df.iloc[-1]['收盘']

    prices = sorted(chip_dict.keys())
    volumes = [chip_dict[p] for p in prices]
    total_chips = sum(volumes)

    # 1. 平均成本
    avg_cost = np.average(prices, weights=volumes)

    # 2. 获利盘比例 (Profit Ratio)
    profit_chips = sum([chip_dict[p] for p in prices if p < current_price])
    profit_ratio = (profit_chips / total_chips) * 100

    # 3. 成本乖离率 (Deviation) - 衡量“获利盘想砸盘的冲动”
    deviation = (current_price - avg_cost) / avg_cost * 100

    # 4. 近端支撑真空度 (Vacuum Check) - 衡量“下方有没有人接”
    # 检查现价下方 10% 区间内的筹码堆积情况
    support_zone_low = current_price * 0.90
    support_chips = sum([chip_dict[p] for p in prices if support_zone_low < p < current_price])
    support_ratio = (support_chips / total_chips) * 100

    return {
        "prices": prices,
        "volumes": volumes,
        "current_price": current_price,
        "avg_cost": avg_cost,
        "profit_ratio": profit_ratio,
        "deviation": deviation,
        "support_ratio": support_ratio
    }


def analyze_recent_forces(df, days=5):
    """
    【力度模块】(大佬说的：看前几个板的走势)
    分析最近 N 天的K线形态，判断是“一致更强”还是“分歧转弱”
    """
    recent_df = df.tail(days).copy()

    # 简单的涨停判定 (非创业板/科创板按10%算，实际应查表)
    # 这里粗略判断：收盘价涨幅 > 9%
    limit_up_count = 0
    rotten_board_count = 0  # 烂板/大分歧数量
    huge_volume_count = 0  # 巨量天数

    avg_vol_month = df['成交量'].tail(20).mean()

    for i, row in recent_df.iterrows():
        pct_chg = row['涨跌幅']

        # 判断是否涨停
        if pct_chg > 9.5:
            limit_up_count += 1

        # 判断是否烂板/大分歧 (长上影线 或 巨量滞涨)
        open_p = row['开盘']
        close_p = row['收盘']
        high_p = row['最高']

        upper_shadow = (high_p - max(open_p, close_p)) / close_p
        is_huge_vol = row['成交量'] > 1.8 * avg_vol_month

        if is_huge_vol:
            huge_volume_count += 1

        # 烂板定义：巨量且有上影线，或者巨量但实体很小
        if (upper_shadow > 0.03) or (is_huge_vol and abs(pct_chg) < 3):
            rotten_board_count += 1

    return {
        "limit_ups": limit_up_count,
        "rotten_boards": rotten_board_count,
        "huge_vols": huge_volume_count,
        "last_close": df.iloc[-1]['收盘'],
        "last_high": df.iloc[-1]['最高'],
        "last_low": df.iloc[-1]['最低']
    }


def generate_strategy_report(stock_code, chip_metrics, force_metrics):
    """
    【策略生成器】
    综合筹码和力度，输出大佬风格的操盘计划
    """
    cp = chip_metrics['current_price']
    dev = chip_metrics['deviation']
    prof = chip_metrics['profit_ratio']
    sup = chip_metrics['support_ratio']

    rotten = force_metrics['rotten_boards']
    limit_ups = force_metrics['limit_ups']

    # 计算明日关键点位
    # 粗略计算10%跌停板，严谨需根据板块区分
    limit_down_price = round(cp * 0.9, 2)
    buy_zone_top = round(cp * 0.94, 2)
    buy_zone_bottom = round(cp * 0.92, 2)

    print("\n" + "#" * 50)
    print(f"🚀 股票代码：{stock_code} | 复盘分析报告")
    print("#" * 50)

    print(f"\n【1. 筹码结构 (大佬视角)】")
    print(f"   - 获利盘比例: {prof:.2f}% {'(⚠️ 极度获利)' if prof > 80 else ''}")
    print(f"   - 成本乖离率: {dev:.2f}%  {'(⚠️ 抛压极大)' if dev > 20 else '(安全)'}")
    print(f"   - 下方真空度: {'⚠️ 悬空 (下方10%无筹码支撑)' if sup < 10 else f'良好 (支撑度{sup:.1f}%)'}")

    print(f"\n【2. 前期走势 (力度识别)】")
    if limit_ups > 0:
        print(f"   - 最近5天出现 {limit_ups} 个涨停板。")
    if rotten > 0:
        print(f"   - ⚠️ 出现 {rotten} 次烂板/大分歧 (放量/长上影)。")
        print("     -> 说明主力且战且退，或者分歧巨大，筹码交换剧烈。")
    else:
        print("   - 走势较稳，未出现明显烂板。")

    print(f"\n【3. 明日做T与操盘预期】")

    # === 核心策略逻辑 ===
    is_dangerous_chips = (dev > 20 and prof > 80)  # 筹码脏
    is_bad_trend = (rotten > 0)  # 走势烂

    if is_dangerous_chips:
        print("🚩 综合判定：【强分歧·博弈反核】")
        print("   (原因：大家都赚大钱了 + 筹码断层，极易踩踏)")

        print("\n👉 剧本 A (符合大佬预期)：")
        print(f"   1. 【高开/冲高】：必须卖！")
        print(f"      - 因为筹码脏，主力会借高开出货。")
        print(f"   2. 【急杀不破】：")
        print(f"      - 观察跌停价 {limit_down_price}。")
        print(f"      - 如果杀到 {buy_zone_bottom} ~ {buy_zone_top} 附近，且【没碰地板】直接拉起。")
        print(f"      - 动作：买回 (做T成功，吃到恐慌盘的血肉)。")

        print("\n👉 剧本 B (低于预期)：")
        print(f"   - 直接封死跌停 {limit_down_price}。")
        print(f"   - 动作：不接！千万别接！说明主力跑了。")

    elif dev < -15:
        print("🚩 综合判定：【超跌磨底】")
        print("   - 上方全是套牢盘，反弹就是卖点，除非放巨量突破。")

    else:
        print("🚩 综合判定：【趋势跟随】")
        print("   - 筹码结构尚可，沿5日线操作。若急跌可低吸，但不宜重仓博弈。")

    print("#" * 50)


def plot_chips(metrics, stock_code):
    """画图模块"""
    prices = metrics['prices']
    volumes = metrics['volumes']
    curr = metrics['current_price']

    plt.figure(figsize=(10, 5))
    plt.barh(prices, volumes, height=(max(prices) - min(prices)) / 100, color='gray', alpha=0.5, label='筹码分布')
    plt.axhline(curr, color='red', linestyle='--', linewidth=2, label='当前价')
    plt.axhline(metrics['avg_cost'], color='blue', linestyle='-.', linewidth=2, label='平均成本')

    # 标记真空区
    plt.axhspan(curr * 0.9, curr, color='yellow', alpha=0.2, label='下方10%空间')

    plt.title(f"Chip Structure: {stock_code}")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.show()


# ================= 主程序 =================
if __name__ == "__main__":
    # 1. 获取数据
    df = get_data(STOCK_CODE)

    if df is not None:
        # 2. 计算筹码
        chip_metrics = calculate_chip_structure(df)

        # 3. 分析力度 (前几个板走势)
        force_metrics = analyze_recent_forces(df)

        # 4. 输出报告
        generate_strategy_report(STOCK_CODE, chip_metrics, force_metrics)

        # 5. 画图
        plot_chips(chip_metrics, STOCK_CODE)