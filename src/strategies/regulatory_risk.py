import akshare as ak
import pandas as pd
import time
from datetime import datetime, timedelta

# ==========================================
# F佬策略配置
# ==========================================
CONFIG = {
    'monitoring_window_10': 10,  # 10日异动窗口
    'monitoring_limit_10': 1.0,  # 100% 涨幅限制 (严重异动线)
    'monitoring_window_30': 30,  # 30日异动窗口
    'monitoring_limit_30': 2.0,  # 200% 涨幅限制
    'concepts': ['商业航天', '卫星导航', '大消费', '零售', '无人驾驶', '互联网金融']  # F佬关注的板块关键词
}


def get_limit_up_pool(date_str):
    """获取指定日期的涨停梯队数据"""
    print(f"🔥 正在拉取 {date_str} 的涨停梯队和连板数据...")
    try:
        # akshare 获取涨停池
        df = ak.stock_zt_pool_em(date=date_str)
        # 必须包含列：代码, 名称, 连板数, 所属行业
        return df
    except Exception as e:
        print(f"获取涨停数据失败: {e}")
        return pd.DataFrame()


def calculate_regulatory_risk(code, current_close):
    """
    计算监管异动风险 (核心算法)
    逻辑：主力如果想拉升，必须确保拉升后不触发 10日100% 或 30日200%
    """
    try:
        # 获取过去40天数据以计算窗口期
        # 注意：这里简化处理，直接用日线涨幅，交易所实际算法包含指数偏离值，但绝对涨幅足够做参考
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")

        df_hist = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date,
                                     adjust="qfq")

        if df_hist.empty or len(df_hist) < 30:
            return None

        # 1. 计算10日累计涨幅 (最近10个交易日)
        # 假设今天是第N天，比较对象是 N-10 天的收盘价
        if len(df_hist) >= 10:
            price_10_days_ago = df_hist.iloc[-11]['收盘']  # 取前10天的基准
            pct_10 = (current_close - price_10_days_ago) / price_10_days_ago
        else:
            pct_10 = 0

        # 2. 计算30日累计涨幅
        if len(df_hist) >= 30:
            price_30_days_ago = df_hist.iloc[-31]['收盘']
            pct_30 = (current_close - price_30_days_ago) / price_30_days_ago
        else:
            pct_30 = 0

        # 3. 计算“安全空间”：如果要再涨一个板(10%)，是否会触发异动？
        potential_price = current_close * 1.1
        potential_pct_10 = (potential_price - price_10_days_ago) / price_10_days_ago

        status = "安全"
        risk_level = 0

        if pct_10 > 0.9 or pct_30 > 1.9:
            status = "高危(需控异动)"  # F佬说的“控异动”
            risk_level = 2
        elif potential_pct_10 > 1.0:
            status = "压线(再涨停即触发)"  # 这种主力可能不敢封板，适合做T或断板
            risk_level = 1
        else:
            status = "空间大(适合二波/接力)"  # 这种最适合做“二波”或“补涨”

        return {
            '10日涨幅': round(pct_10 * 100, 2),
            '30日涨幅': round(pct_30 * 100, 2),
            '异动状态': status,
            '风险等级': risk_level
        }

    except Exception as e:
        return None


def analyze_f_lao_strategy():
    # 1. 获取周五(12.26/12.27)的涨停数据
    # 请注意：如果是周日运行，需要指定上一个交易日
    last_trading_date = '20251226'
    df_zt = get_limit_up_pool(last_trading_date)

    if df_zt.empty:
        print("未获取到涨停数据，请检查日期或网络。")
        return

    results = []

    print(f"🚀 开始分析 {len(df_zt)} 只核心涨停股的【监管空间】...")

    for idx, row in df_zt.iterrows():
        code = row['代码']
        name = row['名称']
        lz = row['连板数']  # 连板梯队
        industry = row['所属行业']
        current_close = row['最新价']

        # 只有连板股或者高辨识度的首板才入 F佬 的法眼
        # 这里我们筛选：连板 >= 2 OR (连板=1 且 属于热门板块)
        is_hot_concept = any(c in industry for c in CONFIG['concepts'])

        if lz >= 2 or is_hot_concept:
            # 计算异动
            reg_data = calculate_regulatory_risk(code, current_close)

            if reg_data:
                item = {
                    '代码': code,
                    '名称': name,
                    '连板数': f"{lz}板",
                    '板块': industry,
                    '现价': current_close,
                    '10日累计涨幅%': reg_data['10日涨幅'],
                    'F佬异动判断': reg_data['异动状态'],
                    '操作建议': ''
                }

                # F佬逻辑映射
                if reg_data['风险等级'] == 2:
                    item['操作建议'] = '⚠️ 必须控异动 (可能断板/做T/横盘)'
                elif reg_data['风险等级'] == 1:
                    item['操作建议'] = '👀 压线时刻 (谨慎接力，博弈主力控盘)'
                else:
                    item['操作建议'] = '🚀 空间充足 (若板块强，可猛干)'

                # 结合F佬提到的板块加分
                if '航空' in industry or '航天' in industry:
                    item['操作建议'] += ' [航天核心]'
                elif '商业' in industry or '零售' in industry:
                    item['操作建议'] += ' [消费核心]'

                results.append(item)
                print(f"分析完成: {name} - {reg_data['异动状态']}")

    # 结果转DataFrame并排序
    df_res = pd.DataFrame(results)
    # 按连板高度排序，高度越高越核心
    if not df_res.empty:
        df_res = df_res.sort_values(by=['连板数', '10日累计涨幅%'], ascending=[False, False])

        print("\n" + "=" * 60)
        print("【F佬模式 · 周一核心作战地图】")
        print("=" * 60)
        # 展示高标核心
        print(df_res[['名称', '连板数', '板块', '10日累计涨幅%', 'F佬异动判断', '操作建议']].to_string())

        # 导出
        df_res.to_excel(f"F_Lao_Strategy_{last_trading_date}.xlsx", index=False)
        print(f"\n详细表格已生成: F_Lao_Strategy_{last_trading_date}.xlsx")


if __name__ == "__main__":
    analyze_f_lao_strategy()