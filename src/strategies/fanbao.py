import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


def check_fanbao_strategy(symbol, start_date, end_date):
    """
    验证单只股票是否符合【完胜反包/涨停反包】策略
    条件：
    1. 前一天收阴
    2. 当天收阳，且收盘价 > 前一天最高价 (反包)
    3. 当天放量 (Vol > Prev Vol)
    4. 当天涨幅 > 9.5% (模拟涨停或强势大阳)
    """
    try:
        # 获取个股历史数据 (日频)
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust="qfq")

        if df.empty or len(df) < 2:
            return False

        # 获取最后两天的数据用于比对
        # T日 (今天/最近交易日)
        today = df.iloc[-1]
        # T-1日 (前一交易日)
        prev_day = df.iloc[-2]

        # --- 条件判断 ---

        # 1. 前阴后阳紧挨在一起
        # 前一日收盘 < 前一日开盘 (阴线)
        cond_prev_yin = prev_day['收盘'] < prev_day['开盘']
        # 今日收盘 > 今日开盘 (阳线)
        cond_today_yang = today['收盘'] > today['开盘']

        # 2. 阳线收盘价必需高于阴线最高价 (核心反包条件)
        cond_engulf = today['收盘'] > prev_day['最高']

        # 3. 后阳需放量 (今日成交量 > 昨日成交量)
        cond_volume = today['成交量'] > prev_day['成交量']

        # 4. 涨幅要求 (图片手写>4%，你要求涨停，这里设为 > 9.5% 以覆盖主板涨停)
        cond_limit_up = today['涨跌幅'] > 9.5

        # 综合判断
        if cond_prev_yin and cond_today_yang and cond_engulf and cond_volume and cond_limit_up:
            return True, today['日期'], today['涨跌幅']

        return False, None, None

    except Exception as e:
        # print(f"Error checking {symbol}: {e}")
        return False, None, None


def run_screener():
    # 设置回测/选股时间段 (例如查看最近几天的信号)
    # 注意：实际选股时，通常选特定某一天是否触发
    target_date_str = datetime.now().strftime("%Y%m%d")
    start_date_str = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    print(f"开始选股，策略：图片【完胜反包战法】+ 涨停...")

    # 1. 获取所有A股代码 (为了演示速度，这里仅演示如何获取列表，建议实盘时先缩小范围)
    # 实际上全市场扫描非常慢，建议先获取这一天的涨停股池，再反查形态，这样效率最高

    try:
        # 获取今日/最近交易日的涨停股池 (这是最高效的方法)
        # 如果是盘后，可以用 date=target_date_str
        # 这里的date需要是最近的一个交易日，例如 '20231215'
        # 为保证代码可运行，这里假设我们要筛选的是特定日期的行情
        recent_trade_date = "20251217"  # 请修改为你想要筛选的具体日期！！！

        print(f"正在获取 {recent_trade_date} 的涨停股池进行形态过滤...")
        limit_up_pool = ak.stock_zt_pool_em(date=recent_trade_date)

        results = []

        if limit_up_pool.empty:
            print("该日期无数据或非交易日。")
            return

        total = len(limit_up_pool)
        print(f"当日涨停个股共 {total} 只，开始形态匹配...")

        for index, row in limit_up_pool.iterrows():
            code = row['代码']
            name = row['名称']

            # 对涨停股进行形态回测
            is_match, date, pct = check_fanbao_strategy(code, start_date_str, recent_trade_date)

            if is_match:
                print(f"[选中] 代码:{code} 名称:{name} 日期:{date} 涨幅:{pct}%")
                results.append({'代码': code, '名称': name, '日期': date})

        # 输出结果
        if results:
            print("\n=== 符合图片模式的股票 ===")
            df_res = pd.DataFrame(results)
            print(df_res)
        else:
            print("没有找到符合条件的股票。")

    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    run_screener()