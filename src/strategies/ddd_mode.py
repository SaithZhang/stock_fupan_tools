
# ==============================================================================
# 💎 DDD 竞价模式 (DDD_Strategy)
# Core Logic: Volume Gates & Tiered Thresholds
# ==============================================================================

# src/strategies/ddd_mode.py

def check_ddd_strategy(row_live, history_item):
    """
    DDD 竞价模式核心逻辑 (1月11日新规版)

    Args:
        row_live (dict): Akshare实时数据 {'code', 'name', 'auc_amt'(元), 'open_pct'(%), ...}
        history_item (dict): 本地昨日数据 {'turnover'(元), 'circ_mv'(元), 'board_count', 'last_bid_amt'(元)}

    Returns:
        tuple: (Score [0-100], Decision_String, Tag_String)
    """

    # --- 1. 数据清洗与解包 ---
    try:
        # 实时数据
        bid_amt_today = float(row_live.get('auc_amt', 0))
        bid_pct = float(row_live.get('open_pct', 0))

        # 历史数据 (务必确保 data_loader 已经处理好单位，这里默认全是 元)
        # 如果您的 data_loader 存的是 'yest_amt'，请在这里做映射
        turnover_prev = float(history_item.get('turnover', 0))
        circ_mv = float(history_item.get('circ_mv', 0))
        boards = int(history_item.get('board_count', 0))
        bid_amt_prev = float(history_item.get('last_bid_amt', 0))

    except (ValueError, TypeError):
        return 0, "", "数据错误"

    # --- 2. 基础风控 ---
    # 竞价必须 > 1.8% (任何连板模式的基础)
    if bid_pct < 1.8:
        return 0, "", ""

    # --- 3. 分组逻辑 ---

    # === Pool A: 1进2 (Yesterday 1 Board) ===
    if boards == 1:
        # 硬门槛：竞价必须 > 3.7%
        if bid_pct < 3.7:
            return 0, "", ""

        # 竞昨成额比 < 18% (防止一致性过高)
        if turnover_prev > 0 and (bid_amt_today / turnover_prev) > 0.18:
            return 0, "", "Fail:竞昨比>18%"

        # --- Volume Gate (Max Logic) ---
        # Tier 1: 微盘 (< 20亿)
        if circ_mv < 20_0000_0000:
            gate_value = max(0.0095 * circ_mv, 0.06 * turnover_prev)
            tier_tag = "微盘"
        # Tier 2: 小盘 (20~27亿)
        elif 20_0000_0000 <= circ_mv < 27_0000_0000:
            gate_value = max(0.0078 * circ_mv, 0.06 * turnover_prev)
            tier_tag = "小盘"
        # Tier 3: 中大盘 (> 27亿)
        else:
            gate_value = max(0.0082 * circ_mv, 0.06 * turnover_prev)
            tier_tag = "中大盘"

        if bid_amt_today > gate_value:
            # 满足条件
            score = 85
            if bid_pct > 5.0: score += 5

            # 计算竞昨比用于显示
            ratio_val = (bid_amt_today / turnover_prev) * 100 if turnover_prev else 0
            detail_msg = f"阈值:{int(gate_value / 10000)}w|实际:{int(bid_amt_today / 10000)}w"
            return score, f"💎DDD/1进2({tier_tag})", detail_msg

    # === Pool B: 2进3 (Yesterday 2 Boards) ===
    elif boards == 2:
        if bid_pct <= 3.0: return 0, "", ""

        if bid_amt_prev <= 0: return 0, "", "缺昨日竞价"

        ratio_growth = bid_amt_today / bid_amt_prev
        is_pass = False

        if circ_mv < 27_0000_0000:
            if ratio_growth > 1.7: is_pass = True
        else:
            if ratio_growth > 1.3: is_pass = True

        if is_pass:
            return 90, "💎DDD/2进3", f"竞增比:{ratio_growth:.2f}"

    # === Pool C: 3进4 (Yesterday 3 Boards) ===
    elif boards == 3:
        if bid_pct <= 3.0: return 0, "", ""
        if bid_amt_prev <= 0: return 0, "", ""

        ratio_growth = bid_amt_today / bid_amt_prev
        ratio_bid_cap = bid_amt_today / circ_mv if circ_mv > 0 else 0

        is_pass = False
        # 3进4 必须满足 双重条件
        if circ_mv < 27_0000_0000:
            # 小票: 竞市值比>2% 且 增量>0.9
            if ratio_bid_cap > 0.02 and ratio_growth > 0.9: is_pass = True
        else:
            # 大票: 竞市值比>1.1% 且 增量>0.9
            if ratio_bid_cap > 0.011 and ratio_growth > 0.9: is_pass = True

        if is_pass:
            return 95, "💎DDD/3进4", f"竞值比:{ratio_bid_cap * 100:.1f}%"

    # 其他情况或未通过
    return 0, "", ""