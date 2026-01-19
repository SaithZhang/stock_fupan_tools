# ==============================================================================
# 💎 DDD 竞价模式核心逻辑 (src/strategies/ddd_mode.py)
# Version: 1.0 | Based on 1/13 Update
# ==============================================================================

def get_ddd_pool_category(item):
    """
    【盘后阶段】: 判断股票属于DDD模式的哪个分组
    Args:
        item: 字典，包含 'limit_days' (连板数), 'name' (名称)
    Returns:
        str: 分组标签 (e.g., "DDD/1进2", "DDD/2进3") 或 None
    """
    limit_days = item.get('limit_days', 0)
    name = item.get('name', '')

    # 过滤 ST
    if 'ST' in name.upper():
        return None

    # 分组逻辑
    if limit_days == 1:
        return "DDD/1进2"
    elif limit_days == 2:
        return "DDD/2进3"
    elif limit_days == 3:
        return "DDD/3进4"
    # D佬模式主要关注低位接力，更高位暂不归类或归为妖股观察
    return None


def calculate_ddd_realtime(row, history_item):
    """
    【盘中竞价阶段】: 计算是否满足DDD开仓条件 (9:25分调用)

    Args:
        row: 实时数据 {'open_pct': float, 'auc_amt': float(万), ...}
        history_item: 历史数据 {'circ_mv': float(元), 'yest_amt': float(元), 'boards': int, 'last_bid_amt': float(元)}

    Returns:
        tuple: (score, decision_str, reason_detail)
        score: 打分 (0为不通过, >80为通过)
        decision_str: 决策短语
        reason_detail: 详细原因/数据
    """
    # 1. 基础数据解包与单位统一
    try:
        # 实时数据
        open_pct = float(row.get('open_pct', 0))
        auc_amt_wan = float(row.get('auc_amt', 0))  # 万
        auc_amt_yuan = auc_amt_wan * 10000

        # 历史数据
        circ_mv = float(history_item.get('circ_mv', 0))  # 确保传入是元
        yest_amt = float(history_item.get('yest_amt', 0))  # 昨日总成交(元)
        last_bid_amt = float(history_item.get('last_bid_amt', 0))  # 昨日竞价金额(元)
        boards = int(history_item.get('boards', 0))

        if circ_mv == 0 or yest_amt == 0:
            return 0, "", "数据缺失"

        # --- Patch: 缺失昨日竞价数据时的兜底逻辑 ---
        if last_bid_amt == 0:
            # 假设昨日竞价为昨日成交额的 5% (经验值: 强势股通常5-10%)
            last_bid_amt = yest_amt * 0.05
        # ---------------------------------------

    except Exception:
        return 0, "", "数据解析误"

    # 2. 核心指标计算
    bid_yest_ratio = auc_amt_yuan / yest_amt  # 竞昨成额比
    bid_mv_ratio = auc_amt_yuan / circ_mv  # 竞价/流通市值

    # 3. 全局红线 (Condition 2 & 6)
    if open_pct > 9.8: return 0, "", "一字开"  # 剔除一字
    if open_pct < -5.0: return 0, "", "竞价跌破-5%"  # 剔除深跌

    # 基础门槛 (1.8% or 3%)
    min_pct = 1.8 if circ_mv < 20_0000_0000 else 3.0
    if boards == 1: min_pct = 3.7  # 1进2要求更高

    if open_pct < min_pct:
        return 0, "", f"竞价弱({open_pct}%)"

    # 1进2 最大竞昨比限制 (Condition 4: Max 21%)
    if boards == 1 and bid_yest_ratio > 0.21:
        return 0, "", f"过热(竞昨比{bid_yest_ratio * 100:.1f}%)"

    # 4. 分层逻辑 (Condition 5)
    # 定义体量
    is_micro = circ_mv < 20_0000_0000  # <20亿
    is_small = 20_0000_0000 <= circ_mv < 27_0000_0000  # 20-27亿
    is_large = circ_mv >= 27_0000_0000  # >27亿

    # === 场景 A: 1进2 ===
    if boards == 1:
        pass_gate = False
        threshold_desc = ""

        # 1/13 更新逻辑: 竞昨比最低要求
        min_ratio_req = 0.06  # 默认6%
        if circ_mv < 90_0000_0000:
            # 中小微 < 90亿: 6%~7%
            min_ratio_req = 0.065
        else:
            # 大票 > 90亿: 5%
            min_ratio_req = 0.05

        # 结合市值比例判定 (Table 5)
        mv_req = 0.0
        if is_micro:
            mv_req = 0.0095  # 0.95%
        elif is_small:
            mv_req = 0.0078  # 0.78%
        else:
            mv_req = 0.0082  # 0.82%

        # 逻辑: 竞价金额 > (市值系数 OR 竞昨比系数) 取最大值
        # 即必须满足其中一个非常强，或者整体都很强。
        # 这里按照D佬原文理解：需满足 "今天竞价金额大于 [自由流通市值的X] 或 [竞昨成额比Y]" 中的最大值
        # 简化理解：强度必须足够大。

        val_by_mv = circ_mv * mv_req
        val_by_ratio = yest_amt * min_ratio_req
        gate_amt = max(val_by_mv, val_by_ratio)

        if auc_amt_yuan >= gate_amt:
            score = 90
            return score, "💎DDD/1进2", f"竞额:{int(auc_amt_wan)}w|竞昨比:{bid_yest_ratio * 100:.1f}%"

    # === 场景 B: 2进3 ===
    elif boards == 2:
        # 核心: 竞价今昨比 (Today Bid / Yesterday Bid)
        if last_bid_amt == 0: return 0, "", "缺昨日竞价数据"

        growth_ratio = auc_amt_yuan / last_bid_amt
        req_growth = 1.3 if is_large else 1.7

        if growth_ratio > req_growth:
            return 95, "💎DDD/2进3", f"增量:{growth_ratio:.1f}倍"

    # === 场景 C: 3进4 ===
    elif boards == 3:
        # 核心: 竞市值比 AND 增量
        if last_bid_amt == 0: return 0, "", "缺昨日竞价数据"
        growth_ratio = auc_amt_yuan / last_bid_amt

        pass_mv_ratio = False
        pass_growth = growth_ratio > 0.9

        if is_large:
            if bid_mv_ratio > 0.011: pass_mv_ratio = True  # > 1.1%
        else:
            if bid_mv_ratio > 0.02: pass_mv_ratio = True  # > 2%

        if pass_mv_ratio and pass_growth:
            return 92, "💎DDD/3进4", f"竞值比:{bid_mv_ratio * 100:.1f}%"

    return 0, "", ""