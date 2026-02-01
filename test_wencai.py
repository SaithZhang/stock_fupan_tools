# test_wencai.py
import pywencai
import pandas as pd

# 嘉文的测试脚本
try:
    print(">>> 正在尝试自动拉取同花顺数据...")
    # 模拟你平时导出的字段
    q = "非ST 股票 现价 涨跌幅 所属行业 连续涨停天数 几天几板 涨停原因 首次涨停时间 最终涨跌幅"
    df = pywencai.get(query=q, loop=True)

    if df is not None and not df.empty:
        print(f"✅ 成功！拉取到 {len(df)} 条数据")
        print(df[['code', '股票简介', '所属行业', '连续涨停天数']].head())
    else:
        print("❌ 拉取为空，可能是反爬或网络问题")
except Exception as e:
    print(f"❌ 报错了: {e}")
    print("提示：如果没有安装 Node.js，pywencai 无法运行。")