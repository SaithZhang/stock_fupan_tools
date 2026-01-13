# src/tools/chip_analyzer.py
import akshare as ak
import numpy as np
import warnings

warnings.filterwarnings('ignore')


def get_chip_metrics(stock_code, lookback_days=120):
    """
    计算个股筹码结构指标
    :param stock_code: 6位代码 (str)
    :return: dict or None
    """
    try:
        # 获取日线数据
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")
        df = df.tail(lookback_days).copy()
        df.reset_index(drop=True, inplace=True)

        if df.empty: return None

        # --- 1. 计算筹码分布 ---
        chip_dict = {}
        for index, row in df.iterrows():
            avg_price = (row['最高'] + row['最低'] + row['收盘']) / 3
            turnover = row['换手率'] / 100
            if turnover > 1: turnover = 1

            # 衰减
            for p in list(chip_dict.keys()):
                chip_dict[p] = chip_dict[p] * (1 - turnover)

            # 新增
            p_key = round(avg_price, 2)
            chip_dict[p_key] = chip_dict.get(p_key, 0) + turnover

        # --- 2. 统计指标 ---
        current_price = df.iloc[-1]['收盘']
        prices = sorted(chip_dict.keys())
        volumes = [chip_dict[p] for p in prices]
        total_chips = sum(volumes)

        if total_chips == 0: return None

        avg_cost = np.average(prices, weights=volumes)

        # 获利盘比例
        profit_chips = sum([chip_dict[p] for p in prices if p < current_price])
        profit_ratio = (profit_chips / total_chips) * 100

        # 乖离率 (Deviation)
        deviation = (current_price - avg_cost) / avg_cost * 100

        # 下方10%真空度 (Vacuum)
        support_zone_low = current_price * 0.90
        support_chips = sum([chip_dict[p] for p in prices if support_zone_low < p < current_price])
        support_ratio = (support_chips / total_chips) * 100

        # --- 3. 分析近期力度 (前几天走势) ---
        # 简易版：只看是否出现过烂板(高换手+长上影)
        recent_df = df.tail(5)
        rotten_count = 0
        limit_up_count = 0

        avg_vol = df['成交量'].tail(20).mean()

        for _, r in recent_df.iterrows():
            if r['涨跌幅'] > 9.5: limit_up_count += 1

            upper_shadow = (r['最高'] - max(r['开盘'], r['收盘'])) / r['收盘']
            is_huge_vol = r['成交量'] > 1.8 * avg_vol

            # 烂板定义：放量且有上影线，或放量滞涨
            if (upper_shadow > 0.03 and is_huge_vol) or (is_huge_vol and abs(r['涨跌幅']) < 3):
                rotten_count += 1

        return {
            'profit_ratio': profit_ratio,
            'deviation': deviation,
            'support_ratio': support_ratio,
            'rotten_days': rotten_count,
            'limit_ups': limit_up_count,
            'current_price': current_price
        }

    except Exception as e:
        # print(f"Chip analysis failed for {stock_code}: {e}") # 调试时可打开
        return None


def generate_chip_tag(metrics):
    """
    根据指标生成简短标签
    """
    if not metrics: return ""

    prof = metrics['profit_ratio']
    dev = metrics['deviation']
    sup = metrics['support_ratio']
    rotten = metrics['rotten_days']

    tags = []

    # 1. 风险判定 (大佬逻辑: 筹码脏 + 获利盘大)
    if dev > 20 and prof > 80:
        if sup < 10:
            tags.append("⚠️筹码断层/高抛")
        else:
            tags.append("⚠️获利极多/防砸")

    elif dev < -15:
        tags.append("🟢深套/反弹")

    # 2. 结合力度
    if rotten > 0 and (dev > 10):
        tags.append("👀分歧/烂板")

    return "/".join(tags)