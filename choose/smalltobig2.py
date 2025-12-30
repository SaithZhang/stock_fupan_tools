import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ==========================================
# 策略参数：捕捉“断板妖股”
# ==========================================
CONFIG = {
    'lookback_days': 15,  # 回溯过去15天数据
    'min_limit_ups': 3,  # 过去10天内至少有3个涨停 (捕捉N天M板)
    'risk_limit_10': 0.95,  # 10日涨幅预警线 (95%以上高危)
    'risk_limit_30': 1.95,  # 30日涨幅预警线
}


def get_active_stocks():
    """
    获取全市场活跃股池。
    逻辑：取近期涨幅榜前列 + 换手率活跃的票，避免全市场5000只遍历太慢。
    """
    print("🔍 正在扫描市场活跃资金流向...")
    try:
        # 获取实时行情，按涨幅排序，取前300名作为初筛池
        df_spot = ak.stock_zh_a_spot_em()
        # 过滤北交所、ST (根据个人喜好，F佬一般玩主板核心)
        df_spot = df_spot[~df_spot['代码'].str.startswith(('8', '4'))]
        df_spot = df_spot[~df_spot['名称'].str.contains('ST')]

        # 取涨速最快或涨幅最高的前300只，大概率包含所有妖股
        df_active = df_spot.sort_values(by='涨跌幅', ascending=False).head(300)
        return df_active
    except Exception as e:
        print(f"数据获取失败: {e}")
        return pd.DataFrame()


def analyze_stock_trend(code, name):
    """分析单只股票的 N天M板 状态及监管风险"""
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")

        # 获取日线数据
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")

        if df.empty or len(df) < 15:
            return None

        # 截取最近10天和30天数据
        df_10 = df.tail(10)
        df_30 = df.tail(30)

        current_close = df.iloc[-1]['收盘']

        # 1. 计算涨停次数 (N天M板)
        # 简单判断：涨幅 > 9.5% 视为涨停/摸板 (考虑主板10%和创业板20%)
        limit_up_count = len(df_10[df_10['涨跌幅'] > 9.5])

        # 如果最近10天涨停板少于3个，说明股性不够妖，直接过滤
        if limit_up_count < CONFIG['min_limit_ups']:
            return None

        # 2. 识别是否是连板 (判断最后一天是否涨停)
        is_consecutive = df.iloc[-1]['涨跌幅'] > 9.5 and df.iloc[-2]['涨跌幅'] > 9.5
        status_desc = f"10天{limit_up_count}板"
        if is_consecutive:
            status_desc += " (连板中)"
        else:
            status_desc += " (断板/反包)"

        # 3. 计算 F佬 关注的监管涨幅
        # 10日涨幅：(现价 - 10天前收盘价) / 10天前收盘价
        # 注意：df_10的第1行是 T-9，比较基准应该是 df 的 T-10
        base_price_10 = df.iloc[-11]['收盘']
        pct_10 = (current_close - base_price_10) / base_price_10

        base_price_30 = df.iloc[-31]['收盘'] if len(df) > 30 else df.iloc[0]['收盘']
        pct_30 = (current_close - base_price_30) / base_price_30

        # 4. 判定 F佬 策略建议
        advice = "安全"
        if pct_10 > CONFIG['risk_limit_10']:
            advice = "⚠️ 严重异动压顶 (100%线)"
        elif pct_30 > CONFIG['risk_limit_30']:
            advice = "⚠️ 30日异动压顶 (200%线)"
        else:
            space_left = 1.0 - pct_10
            advice = f"🚀 空间充足 (距100%线还有 {(space_left * 100):.1f}%)"

        return {
            '代码': code,
            '名称': name,
            '现价': current_close,
            '股性': status_desc,
            '10日涨幅%': round(pct_10 * 100, 2),
            '30日涨幅%': round(pct_30 * 100, 2),
            'F佬策略': advice
        }

    except Exception as e:
        return None


def run_f_lao_scanner():
    df_pool = get_active_stocks()
    if df_pool.empty:
        return

    print(f"🔥 正在深度扫描 {len(df_pool)} 只活跃股，寻找 N天M板 妖股...")

    results = []
    count = 0
    total = len(df_pool)

    for idx, row in df_pool.iterrows():
        count += 1
        if count % 50 == 0:
            print(f"进度: {count}/{total}...")

        res = analyze_stock_trend(row['代码'], row['名称'])
        if res:
            results.append(res)

    # 结果处理
    df_final = pd.DataFrame(results)
    if not df_final.empty:
        # 按10日涨幅降序排列，看谁最强
        df_final = df_final.sort_values(by='10日涨幅%', ascending=False)

        print("\n" + "=" * 80)
        print("【F佬模式 · 高标妖股监管扫描 (含断板反包)】")
        print("=" * 80)
        print(df_final[['名称', '股性', '10日涨幅%', 'F佬策略']].to_string())

        file_name = f"F_Lao_Advanced_Scan_{datetime.now().strftime('%Y%m%d')}.xlsx"
        df_final.to_excel(file_name, index=False)
        print(f"\n📄 详细报告已生成: {file_name}")
    else:
        print("未发现符合 N天M板 条件的活跃股。")


if __name__ == "__main__":
    run_f_lao_scanner()