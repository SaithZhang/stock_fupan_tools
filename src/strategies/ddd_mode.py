
# ==============================================================================
# 💎 DDD 竞价模式 (DDD_Strategy)
# Core Logic: Volume Gates & Tiered Thresholds
# ==============================================================================

def check_ddd_strategy(row_live, history_item):
    """
    Check if stock meets DDD Strategy criteria.
    
    Args:
        row_live (dict): Live data from Akshare {'code', 'name', 'auc_amt', 'open_pct', ...}
        history_item (dict): Static history {'yest_amt', 'circ_mv', 'boards', 'yest_bid_amt'}
        
    Returns:
        tuple: (Score [0-100], Decision_String, Tag_String)
               If not qualified or fail, returns (0, "", "")
    """
    
    # 1. Unpack Variables
    code = str(row_live['code'])
    name = str(row_live['name'])
    
    # Live Data (Today)
    bid_amt_today = float(row_live.get('auc', 0)) # Using 'auc' from screener mapping
    bid_pct = float(row_live.get('open_pct', 0))
    
    # History Data (Yesterday)
    circ_mv = float(history_item.get('circ_mv', 0)) # Free Float Cap
    turnover_prev = float(history_item.get('yest_amt', 0))
    bid_amt_prev = float(history_item.get('yest_bid_amt', 0))
    boards_prev = int(history_item.get('boards', 0))
    
    if circ_mv == 0 or turnover_prev == 0:
        return 0, "", ""

    # 2. Key Ratios
    ratio_bid_turnover = bid_amt_today / turnover_prev
    ratio_bid_cap = bid_amt_today / circ_mv
    
    # 3. Determine Pool
    # Pool A: 1->2 (Yesterday was 1 board)
    # Pool B: 2->3 (Yesterday was 2 board)
    # Pool C: 3->4 (Yesterday was 3 board)
    # Only applies if Yesterday was ZT (Limit Up)
    pool_type = ""
    if boards_prev == 1: pool_type = "A"
    elif boards_prev == 2: pool_type = "B"
    elif boards_prev == 3: pool_type = "C"
    
    if not pool_type:
        return 0, "", "" # Not applicable for unrelated stocks
        
    # 4. Filters & Logic
    
    # A. Global Filters
    if bid_pct < 1.8: return 0, "", "" # Weakness Check
    if ratio_bid_turnover > 0.18: return 0, "", "" # Excess Consistency
    
    # B. Specific Pool Logic
    
    # --- POOL A (1 -> 2) ---
    if pool_type == "A":
        # Threshold
        if bid_pct <= 3.7: return 0, "", "" # Strict floor
        
        # Volume Gate (Dynamic Floor - Max Logic)
        gate_value = 0.0
        
        # Tier 1: Micro < 20亿
        if circ_mv < 20_0000_0000:
            gate_value = max(0.0095 * circ_mv, 0.06 * turnover_prev)
            
        # Tier 2: Small 20-27亿
        elif 20_0000_0000 <= circ_mv < 27_0000_0000:
            gate_value = max(0.0078 * circ_mv, 0.06 * turnover_prev)
            
        # Tier 3: Mid/Large > 27亿
        else:
            gate_value = max(0.0082 * circ_mv, 0.06 * turnover_prev)
            
        # Check Condition
        if bid_amt_today > gate_value:
            # Pass
            score = 85
            # Bonus score for Ideal > 5%
            if bid_pct > 5.0: score += 5
            return score, "💎DDD/1进2", f"Gate:{int(gate_value/10000)}w"
            
    # --- POOL B (2 -> 3) ---
    elif pool_type == "B":
        if bid_pct <= 3.0: return 0, "", ""
        
        # Continuous Volume Logic
        if bid_amt_prev <= 0: return 0, "", "" # Data missing
        
        ratio_growth = bid_amt_today / bid_amt_prev
        
        is_pass = False
        if circ_mv < 27_0000_0000:
            if ratio_growth > 1.7: is_pass = True
        else:
            if ratio_growth > 1.3: is_pass = True
            
        if is_pass:
            return 90, "💎DDD/2进3", f"Grw:{ratio_growth:.1f}"

    # --- POOL C (3 -> 4) ---
    elif pool_type == "C":
        if bid_pct <= 3.0: return 0, "", ""
        
        if bid_amt_prev <= 0: return 0, "", ""
        
        ratio_growth = bid_amt_today / bid_amt_prev
        
        is_pass = False
        if circ_mv < 27_0000_0000:
            if ratio_bid_cap > 0.02 and ratio_growth > 0.9: is_pass = True
        else:
            if ratio_bid_cap > 0.011 and ratio_growth > 0.9: is_pass = True
            
        if is_pass:
            return 92, "💎DDD/3进4", f"CapR:{ratio_bid_cap*100:.1f}%"

    return 0, "", ""
