import akshare as ak
import pandas as pd
import datetime
import time

# ==========================================
# 1. 策略配置 (Bolo Strategy Config)
# ==========================================
CONFIG = {
    'start_date': '20250101',  # 获取历史数据的起始时间（只需最近1-2个月计算均线）
    'min_amount': 100000000,  # 最小成交额：1亿 (拨佬喜欢有流动性的票)
    'min_turnover': 5.0,  # 或 最小换手率：5% (活跃股)
    'ma_fast': 5,  # 5日线
    'ma_slow': 10,  # 10日线
    'regulation_limit': 0.95,  # 10日涨幅异动警戒线 (近似值，如95%)
}


def get_market_data():
    """获取全市场实时行情快照"""
    print("🚀 正在拉取全市场实时数据 (Spot Data)...")
    try:
        # 东方财富实时行情
        df_spot = ak.stock_zh_a_spot_em()
        # 过滤掉 ST, 退市, 北交所(看个人喜好，拨佬主要玩主板/创业板核心)
        df_spot = df_spot[~df_spot['名称'].str.contains('ST|退')]
        df_spot = df_spot[~df_spot['代码'].str.startswith('8')]  # 过滤北交所
        df_spot = df_spot[~df_spot['代码'].str.startswith('4')]  # 过滤北交所

        # 初筛：只看活跃股 (成交额>1亿 OR 换手率>5%)
        # 注意：akshare返回的列名可能变化，需确保列名正确
        # 通常列名：['序号', '代码', '名称', '最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '振幅', '最高', '最低', '今开', '昨收', '量比', '换手率', '市盈率-动态', '市净率']
        mask = (df_spot['成交额'] > CONFIG['min_amount']) | (df_spot['换手率'] > CONFIG['min_turnover'])
        df_active = df_spot[mask].copy()

        print(f"✅ 初筛完成，全市场活跃股共 {len(df_active)} 只。准备逐个扫描历史K线...")
        return df_active
    except Exception as e:
        print(f"❌ 获取市场数据失败: {e}")
        return pd.DataFrame()


def analyze_stock(code, name):
    """分析单只股票的历史K线，判断是否符合策略"""
    try:
        # 获取个股历史数据 (日线)
        df_hist = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=CONFIG['start_date'], adjust="qfq")

        if df_hist.empty or len(df_hist) < 15:
            return None

        # 重命名列以方便操作
        df_hist = df_hist.rename(
            columns={'日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume',
                     '换手率': 'turnover', '涨跌幅': 'pct_chg'})

        # 计算均线
        df_hist['MA5'] = df_hist['close'].rolling(window=CONFIG['ma_fast']).mean()
        df_hist['MA10'] = df_hist['close'].rolling(window=CONFIG['ma_slow']).mean()

        # 取最后一天数据 (即周五)
        last_day = df_hist.iloc[-1]
        prev_day = df_hist.iloc[-2]  # 周四

        result = {}
        matched = False

        # ====================================================
        # 策略 1: 弱转强预备 (寻找炸板、烂板、大分歧)
        # ====================================================
        # 逻辑：最高价曾触及涨停(>9%)，但收盘回落；或者长上影线；或者爆量阴线

        is_limit_touched = last_day['high'] >= last_day['low'] * 1.09  # 简易摸板判断
        is_broken = is_limit_touched and (last_day['close'] < last_day['high'])  # 炸板/回落
        is_big_divergence = last_day['turnover'] > 15  # 高换手分歧

        if is_broken:
            result['type'] = '【弱转强预备】(炸板/烂板)'
            result['reason'] = f"曾摸板，收盘回落，换手{last_day['turnover']}%"
            result['strategy'] = "周一竞价若高开+爆量(昨日量能5-10%)，可试错。"
            matched = True
        elif is_big_divergence and last_day['pct_chg'] > 0:
            result['type'] = '【分歧转一致预备】'
            result['reason'] = f"高换手{last_day['turnover']}%且收红"
            result['strategy'] = "观察承接力度，若主要均线不破可博弈。"
            matched = True

        # ====================================================
        # 策略 2: 趋势中军低吸 (MA5/MA10战法)
        # ====================================================
        # 逻辑：趋势向上 (MA5 > MA10)，股价回踩MA5或MA10附近企稳

        if not matched:  # 互斥，优先看弱转强，再看趋势
            # 趋势向上
            trend_up = last_day['MA5'] > last_day['MA10']
            # 距离MA5很近 (比如差距在 ±2% 以内) 或者 在 MA5 和 MA10 之间
            dist_ma5 = abs(last_day['close'] - last_day['MA5']) / last_day['MA5']
            in_buy_zone = (last_day['low'] <= last_day['MA5'] * 1.01) and (last_day['close'] >= last_day['MA10'])

            if trend_up and in_buy_zone and dist_ma5 < 0.03:
                result['type'] = '【趋势低吸】'
                result['reason'] = f"回踩5日线(MA5:{last_day['MA5']:.2f})，趋势未破"
                result['strategy'] = "沿5日线低吸，有效跌破离场。"
                matched = True

        # ====================================================
        # 风险监控: 10日涨幅
        # ====================================================
        if matched:
            # 计算最近10天涨幅
            recent_10 = df_hist.iloc[-10:]
            period_start = recent_10.iloc[0]['close']
            period_end = recent_10.iloc[-1]['close']
            pct_10_days = (period_end - period_start) / period_start

            result['10日涨幅'] = f"{pct_10_days * 100:.2f}%"
            if pct_10_days > 0.8:  # 接近100%
                result['reason'] += " ⚠️注意异动监管"

            result['code'] = code
            result['name'] = name
            result['close'] = last_day['close']
            result['pct'] = last_day['pct_chg']
            return result

    except Exception as e:
        # print(f"Error analyzing {code}: {e}")
        return None

    return None


def run_scanner():
    # 1. 获取活跃股
    df_active = get_market_data()

    if df_active.empty:
        print("未获取到数据，请检查网络。")
        return

    bolo_pool = []

    # 2. 遍历扫描 (为了演示，你可以先取前100个测试，正式跑去掉 .head(100))
    # print("⏳ 开始深度扫描（这可能需要几分钟，请耐心等待）...")

    total = len(df_active)
    count = 0

    for index, row in df_active.iterrows():
        count += 1
        code = row['代码']
        name = row['name'] if 'name' in row else row['名称']

        # 打印进度条
        if count % 50 == 0:
            print(f"正在分析: {count}/{total} ...")

        res = analyze_stock(code, name)
        if res:
            bolo_pool.append(res)

    # 3. 输出结果
    if not bolo_pool:
        print("没有筛选到符合条件的股票。")
        return

    df_result = pd.DataFrame(bolo_pool)

    # 导出到Excel
    filename = f"Bolo_Strategy_Plan_{datetime.date.today()}.xlsx"
    df_result.to_excel(filename, index=False)

    print("\n" + "=" * 50)
    print(f"🎉 复盘完成！共选出 {len(df_result)} 只标的")
    print(f"📄 结果已保存至: {filename}")
    print("=" * 50)

    # 在控制台打印重点 (按类型分组)
    print("\n--- 弱转强预备 (周一重点看竞价) ---")
    print(df_result[df_result['type'].str.contains('弱转强')][['code', 'name', 'pct', 'reason']].to_string())

    print("\n--- 趋势低吸 (周一关注水下机会) ---")
    print(df_result[df_result['type'].str.contains('趋势')][['code', 'name', 'close', 'reason']].head(10).to_string())


if __name__ == "__main__":
    run_scanner()