# ==============================================================================
# 💎 DDD 竞价模式核心逻辑 (src/strategies/ddd_mode.py)
# Version: 1.2 | 优化: 增加强力比率豁免，防止误杀广电电气等强票
# ==============================================================================

# ================= 📜 策略逻辑映射 =================
DDD_STRATEGY_LOGIC = """
【核心优化】
1. 1进2逻辑中，如果 竞昨比 > 7.5% (表现极强)，即使未达到市值系数要求，
   也给予 "Weak Pass" (弱通过/观察)，防止因市值数据偏差导致漏单。
"""
# ===================================================

def get_ddd_pool_category(item):
    """【盘后】判断属于哪个分组"""
    limit_days = item.get('limit_days', 0)
    name = item.get('name', '')
    if 'ST' in name.upper(): return None
    if limit_days == 1: return "DDD/1进2"
    elif limit_days == 2: return "DDD/2进3"
    elif limit_days == 3: return "DDD/3进4"
    return None

def calculate_ddd_realtime(row, history_item):
    """【盘中】计算DDD条件"""
    try:
        open_pct = float(row.get('open_pct', 0))
        auc_amt_wan = float(row.get('auc_amt', 0))
        auc_amt_yuan = auc_amt_wan * 10000
        circ_mv = float(history_item.get('circ_mv', 0)) 
        yest_amt = float(history_item.get('yest_amt', 0))
        last_bid_amt = float(history_item.get('last_bid_amt', 0))
        boards = int(history_item.get('boards', 0))

        if circ_mv == 0 or yest_amt == 0: return 0, "", "数据缺失"
        if last_bid_amt == 0: last_bid_amt = yest_amt * 0.05

    except: return 0, "", "解析错误"

    # 指标计算
    bid_yest_ratio = auc_amt_yuan / yest_amt
    bid_mv_ratio = auc_amt_yuan / circ_mv

    # 全局风控
    if open_pct > 9.8: return 0, "", "一字开(剔除)"
    if open_pct < -5.0: return 0, "", "竞价核按钮"

    # 涨幅门槛
    base_min_pct = 1.8 if circ_mv < 20_0000_0000 else 3.0
    if boards == 1:
        if open_pct < 3.7: return 0, "", f"1进2涨幅不足({open_pct}%)"
    else:
        if open_pct < base_min_pct: return 0, "", f"抢筹弱({open_pct}%)"

    # 分层定义
    is_micro = circ_mv < 20_0000_0000
    is_small = 20_0000_0000 <= circ_mv < 27_0000_0000
    is_large_mv = circ_mv >= 27_0000_0000
    is_huge = circ_mv >= 90_0000_0000

    # ➤ 1进2 逻辑
    if boards == 1:
        if bid_yest_ratio > 0.21: return 0, "", f"过热(竞昨比{bid_yest_ratio*100:.1f}%)"

        ratio_req = 0.05 if is_huge else 0.06
        
        if is_micro: mv_req = 0.0095
        elif is_small: mv_req = 0.0078
        else: mv_req = 0.0082

        val_mv = circ_mv * mv_req
        val_ratio = yest_amt * ratio_req
        gate_amt = max(val_mv, val_ratio)

        # [优化] 豁免逻辑: 竞昨比非常强(>7.5%)，但竞额稍差，给80分观察
        is_ratio_super = bid_yest_ratio >= 0.075

        if auc_amt_yuan >= gate_amt:
            score = 90
            msg = "🔥强" if is_ratio_super else ""
            return score, "DDD/1进2", f"{msg}竞额:{int(auc_amt_wan)}w|比:{bid_yest_ratio*100:.1f}%"
        
        # [新增] 广电电气补丁: 如果未达标，但竞昨比很高(>7.5%)，且差额在20%以内
        if is_ratio_super and auc_amt_yuan >= gate_amt * 0.8:
            return 80, "DDD/1进2(观察)", f"⚠️竞额弱|比率强:{bid_yest_ratio*100:.1f}%"
            
        missing = int((gate_amt - auc_amt_yuan)/10000)
        return 0, "", f"强度不足(差{missing}w)"

    # ➤ 2进3 逻辑
    elif boards == 2:
        if last_bid_amt == 0: return 0, "", "缺昨日竞价"
        growth = auc_amt_yuan / last_bid_amt
        req = 1.3 if is_large_mv else 1.7
        if growth > req: return 95, "DDD/2进3", f"增量:{growth:.1f}倍"
        return 0, "", f"增量不足({growth:.1f})"

    # ➤ 3进4 逻辑
    elif boards == 3:
        if last_bid_amt == 0: return 0, "", "缺昨日竞价"
        growth = auc_amt_yuan / last_bid_amt
        pass_mv = (is_large_mv and bid_mv_ratio > 0.011) or (not is_large_mv and bid_mv_ratio > 0.02)
        if pass_mv and growth > 0.9:
            return 92, "DDD/3进4", f"竞值比:{bid_mv_ratio*100:.1f}%"
        return 0, "", f"3进4弱(比{bid_mv_ratio*100:.1f}%)"

    return 0, "", "未定义连板"