import akshare as ak
import pandas as pd

# 设置显示所有列
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

print("🚀 正在尝试从 [东方财富] 获取美利云(000815) 分时数据...")

try:
    # 注意：这里使用的是 _em 后缀的函数，专门走东方财富接口
    # symbol 需要去掉 sz/sh 前缀，直接用数字
    df = ak.stock_zh_a_hist_min_em(symbol="000815", period="1", adjust="qfq")

    # 截取今天的数据（东财这个接口有时会返回最近几天的）
    # 获取今天的日期字符串
    today = pd.Timestamp.now().strftime('%Y-%m-%d')
    df['时间'] = pd.to_datetime(df['时间'])
    df_today = df[df['时间'].dt.strftime('%Y-%m-%d') == today]

    if df_today.empty:
        print("⚠️ 东财接口暂未返回今日数据，尝试显示最后60条数据：")
        print(df.tail(60))
    else:
        print(f"✅ 成功获取今日 ({today}) 分时数据：")
        print(df_today.tail(60))  # 打印最近60分钟

except Exception as e:
    print(f"❌ 东方财富接口报错: {e}")