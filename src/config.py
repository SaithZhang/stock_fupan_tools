# src/config.py

class ProjectConfig:
    # ================= 策略通用配置 =================
    
    # 弱转强：竞价金额占流通市值比 ( min 1.0% = 强)
    WEAK_TO_STRONG_MV_RATIO = 1.0
    
    # 弱转强：平盘震荡区 (-2% ~ 1.8%) 最小量能要求
    WEAK_TO_STRONG_SHOCK_MV_RATIO = 0.8
    
    # 竞价/昨日成交额 占比区间 (单位: %)
    AUCTION_RATIO_MIN = 3.0
    AUCTION_RATIO_MAX = 18.0
    AUCTION_RATIO_RECOMMEND_MIN = 5.0
    AUCTION_RATIO_RECOMMEND_MAX = 15.0

    # ================= 情绪周期配置 =================
    
    # 情绪周期阶段定义
    PHASE_RISING = "Rising"             # 上升期 (连板高度上升, 跌停少)
    PHASE_DIVERGENCE = "Divergence"     # 分歧期 (高位震荡, 炸板率高)
    PHASE_DECLINE = "Decline"           # 退潮期 (连板高度下降, 跌停增多)
    PHASE_ICE_POINT = "Ice Point"       # 冰点期 (连板高度极低, 所谓"冰点")

    # 冰点标准 (连板最高高度 <= 3板)
    ICE_POINT_HEIGHT = 3
    
    # 退潮标准 (昨日涨停今日平均收益 < 0)
    DECLINE_AVG_PROFIT = 0.0

    # ================= 监管配置 =================
    # 异动监管阈值
    RISK_LIMIT_10_DAYS = 0.95  # 10日涨幅 > 95%
    RISK_LIMIT_30_DAYS = 1.95  # 30日涨幅 > 195%
