import akshare as ak

# 测试行业接口
try:
    df = ak.stock_board_industry_cons_em(symbol="消费电子")
    print(f"✅ 行业接口获取成功: {len(df)} 只股票")
except:
    print("❌ 行业接口获取失败")

# 测试概念接口
try:
    df = ak.stock_board_concept_cons_em(symbol="消费电子")
    print(f"✅ 概念接口获取成功: {len(df)} 只股票")
except:
    print("❌ 概念接口获取失败")