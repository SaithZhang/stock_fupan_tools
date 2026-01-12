# ==============================================================================
# 📌 F佬/Bo佬 盘中实时作战指挥室 (src/monitors/intraday_monitor.py) - 【盘中常驻运行】
# v1.1 核心辅导版 - 引入 post-market 模块共享数据加载
# Last Modified: 2026-01-11
# ==============================================================================
import pandas as pd
import akshare as ak
import os
import sys
import re
import time
import datetime
import json
from colorama import init, Fore, Style, Back

# 解决 Windows 终端输出编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# Append PROJECT_ROOT to sys.path to allow imports from src
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import load_holdings, load_pool_full, load_history_basics, load_manual_focus, HOLDINGS_PATH, STRATEGY_POOL_PATH, get_latest_history_path, get_latest_call_auction_file, parse_call_auction_file


# 引入核心模块
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
try:
    from emotion_cycle import EmotionalCycleEngine
except:
    pass

    pass

# Helper to load market sentiment from JSON
def load_market_sentiment_json():
    """Load the latest market_sentiment_YYYYMMDD.json"""
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'output')
    if not os.path.exists(output_dir): return {}
    
    files = [f for f in os.listdir(output_dir) if f.startswith('market_sentiment_') and f.endswith('.json')]
    if not files: return {}
    
    files.sort(reverse=True)
    latest = os.path.join(output_dir, files[0])
    try:
        with open(latest, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


# ================= 🚀 核心策略 =================

def get_market_mood():
    """获取市场情绪：领涨板块 & 全板块列表"""
    try:
        df = ak.stock_board_industry_name_em()
        # 按涨跌幅排序
        df = df.sort_values(by='涨跌幅', ascending=False)
        
        # 1. 领涨前5
        top_5 = df.head(5)
        top_sectors = [f"{row['板块名称']}({row['涨跌幅']}%)" for _, row in top_5.iterrows()]
        summary = " 🔥 ".join(top_sectors)
        
        # 2. 全市场概览 (紧凑排版)
        lines = []
        items = []
        for i, (_, row) in enumerate(df.iterrows()):
            name = row['板块名称']
            pct = row['涨跌幅']
            
            # 颜色装饰
            c = Fore.RED if pct > 0 else (Fore.GREEN if pct < 0 else Fore.WHITE)
            item_str = f"{c}{name}:{pct:>5.2f}%{Style.RESET_ALL}"
            items.append(item_str)
            
            # 每行显示 6 个
            if (i + 1) % 6 == 0:
                lines.append("  ".join(items))
                items = []
        
        if items: lines.append("  ".join(items))
        
        full_detail = "\n".join(lines)
        return summary, full_detail
    except Exception as e:
        return "数据获取中...", f"获取失败: {e}"

def get_index_status():
    """获取大盘状态：上证指数、成交额、量比"""
    info = {
         'price': 0.0, 'pct': 0.0, 
         'sh_amt': 0.0, 'sz_amt': 0.0,
         'sh_vr': 0.0
    }
    try:
        # ak.stock_zh_index_spot_em(symbol="沪深重要指数") 包含上证指数、深证成指
        df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        
        if not df.empty:
            # 上证指数
            sh = df[df['名称'] == '上证指数']
            if not sh.empty:
                item = sh.iloc[0]
                info['price'] = float(item['最新价'])
                info['pct'] = float(item['涨跌幅'])
                info['sh_amt'] = float(item['成交额'])
                info['sh_vr'] = float(item.get('量比', 0))
            
            # 深证成指 (只需要成交额)
            sz = df[df['名称'] == '深证成指']
            if not sz.empty:
                item = sz.iloc[0]
                info['sz_amt'] = float(item['成交额'])
                
    except:
        pass
    return info

def check_signals(row, holding_info, tag, index_pct, current_time_str):
    """
    分析单只股票，生成信号
    row: akshare 实时数据行
    holding_info: 持仓信息 {'cost': x, 'vol': x} 或 None
    tag: 策略标签
    index_pct: 大盘涨跌幅
    """
    is_holding = holding_info is not None
    cost = holding_info.get('cost', 0) if is_holding else 0
    
    try:
        price = float(row['最新价'])
        pct = float(row['涨跌幅'])
        high = float(row['最高'])
        low = float(row['最低'])
        open_p = float(row['今开'])
        
        vr = float(row.get('量比', 0))
        turnover = float(row.get('换手率', 0))
        
        amt = float(row['成交额'])
        vol = float(row['成交量'])
        vwap = price 
        if vol > 0: vwap = amt / (vol * 100)
            
    except:
        return (0, "", "", 0.0, 0.0) # Level, Text, Color, Bias, CostRatio

    signals = []
    
    # 指标计算
    bias = (price - vwap) / vwap * 100
    cost_ratio = (price - cost) / cost * 100 if cost > 0 else 0.0
    
    hour = int(current_time_str.split(':')[0])
    
    # --- 0. 环境风控 ---
    if hour >= 14 and index_pct < -0.5:
        # 尾盘大盘跳水，持仓需谨慎
        if is_holding: signals.append((5, "⚠️尾盘防守", Fore.YELLOW))
    
    # --- 1. 持仓股策略 ---
    if is_holding:
        # A. 卖点
        if bias > 3.0: signals.append((8, "🚀急拉卖T", Fore.MAGENTA))
        if bias > 5.0: signals.append((9, "🚀火箭偏离", Back.MAGENTA))
        
        # B. 买点
        if bias < -3.0: 
            # 只有在大盘不差的时候才敢接
            if index_pct > -0.3:
                signals.append((8, "🌊急杀买T", Fore.CYAN))
            else:
                signals.append((4, "🌊急杀(大盘弱)", Fore.WHITE))
            
        # C. 止损/止盈
        if pct < -4.0 and cost_ratio < -2.0:
             signals.append((7, "⚠️止损提醒", Fore.RED))

    # --- 2. 策略池策略 ---
    else:
        # A. 弱转强
        if open_p < vwap and price > vwap and pct > 1.0:
            if vr > 1.0: signals.append((6, "★弱转强", Fore.RED))
            
        # B. 均线承接
        if abs(bias) < 0.5 and pct > 0: 
             signals.append((4, "👀均线承接", Fore.YELLOW))
             
        # C. 人气扫板
        if "人气" in tag and pct > 8.0 and pct < 9.8:
            signals.append((7, "🔥人气扫板", Fore.RED))

    # 没信号但有异常
    if not signals and vr > 2.5 and pct > 3.0:
        signals.append((3, "👀放量拉升", Fore.WHITE))

    if not signals: return (0, "观察", Fore.WHITE, bias, cost_ratio)
    signals.sort(key=lambda x: x[0], reverse=True)
    
    return (signals[0][0], signals[0][1], signals[0][2], bias, cost_ratio)

def load_call_auction_data():
    """
    Load the latest call auction data using shared utility.
    Returns: 
        dict: {code: {'amount': float, 'pct': float}}, 
        str: timestamp of the file
    """
    file_path = get_latest_call_auction_file()
    if not file_path:
        return {}, ""
    
    # Get timestamp
    mod_time = os.path.getmtime(file_path)
    time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%H:%M:%S')
    filename = os.path.basename(file_path)
    
    try:
        df = parse_call_auction_file(file_path)
        if df is None or df.empty:
             return {}, f"{filename} (Empty)"
             
        data_map = {}
        for _, row in df.iterrows():
            code = row['code']
            # Shared utility returns 'auc_amt' (Wan), 'open_pct'
            # Monitor expects 'amount' (Raw or Wan? See below)
            # The monitor code previously did: 
            # item['call_amt']/10000 in display. so item['call_amt'] should be raw value?
            # Wait, let's check old code logic.
            # Old code: if '万' in val -> parse -> e.g. 100万 -> 1000000. 
            # Then main() does: int(item['call_amt']/10000). So main expects raw value.
            # 
            # Shared `parse_call_auction_file` returns `auc_amt` in *Wan* for large numbers?
            # Let's check `parse_call_auction_file` implementation I just wrote.
            # It says: if pure number -> float(raw)/10000.0 (Wait, pure number 4084080 -> 408.4 Wan)
            # if '亿'/'万' -> eval/float -> e.g. 1.5亿 -> 15000 (Wan, via replace 亿 with *10000).
            # So `parse_call_auction_file` returns unit in **Wan**.
            #
            # Old `intraday_monitor` logic:
            #  val.replace('万', '*10000') -> This implies it wanted Raw Value.
            #  And main() divides by 10000.
            #
            # So if shared utility returns Wan, I need to multiply by 10000 to get Raw Value for `intraday_monitor` compatibility.
            
            amt_wan = row['auc_amt']
            pct = row['open_pct']
            
            data_map[code] = {'amount': amt_wan * 10000, 'pct': pct}
            
        return data_map, f"{filename} ({time_str})"
        
    except Exception as e:
        return {}, f"Error: {str(e)}"


def main():
    print(f"\n{Back.RED}{Fore.WHITE} F佬 · 作战指挥室 (实时监控) {Style.RESET_ALL}")
    
    # 1. 加载名单 (Use Full Pool)
    holdings = load_holdings()
    pool_map_full = load_pool_full()
    manual_map = load_manual_focus() # 加载手动关注，用于强制显示
    history = load_history_basics() # 用来补全名称
    
    # Load Sentiment JSON
    sentiment_json = load_market_sentiment_json()

    # Load Call Auction Data
    call_auction_map, call_source_info = load_call_auction_data()

    
    # 合并监控名单
    monitor_codes = set(holdings) | set(pool_map_full.keys())
    monitor_list = list(monitor_codes)
    
    print(f"🎯 监控目标: {len(monitor_list)} 只 (持仓 {len(holdings)} | 策略 {len(pool_map_full)})")
    
    # 获取行情
    df = ak.stock_zh_a_spot_em()
    
    # 获取大盘情绪
    idx_info = get_index_status()
    index_price = idx_info['price']
    index_pct = idx_info['pct']
    # 计算总成交额 (万亿)
    total_amt = idx_info['sh_amt'] + idx_info['sz_amt']
    total_amt_str = f"{total_amt/1000000000000:.2f}万亿" if total_amt > 1000000000000 else f"{total_amt/100000000:.0f}亿"
    sh_vr = idx_info['sh_vr']
    
    sh_vr = idx_info['sh_vr']
    
    # Extract Sentiment from JSON
    highest_space = sentiment_json.get('highest_space', 0)
    limit_up_count = sentiment_json.get('limit_up_count', 0)
    limit_down_count = sentiment_json.get('limit_down_count', 0)
    prem = sentiment_json.get('yesterday_limit_up_premium', 0.0)
    
    # Extract Sector Inflows from JSON
    inflows = sentiment_json.get('sector_inflows', [])
    inflow_str = " ".join([f"{s['name']}" for s in inflows[:3]]) if inflows else ""
    
    # Extract Sector Gainers from JSON (Overwrite real-time scraping if prefer stable daily view, but real-time is better for monitor)
    # used real-time 'sector_summary' below
    
    sector_summary, sector_detail = get_market_mood()
    
    current_time = datetime.datetime.now().strftime('%H:%M:%S')
    
    # ... (中间省略: 过滤与计算)
    df_target = df[df['代码'].isin(monitor_list)].copy()
    display_list = []
    
    for _, row in df_target.iterrows():
        code = row['代码']
        holding_info = holdings.get(code)
        is_hold = holding_info is not None
        
        # Get Strategy Info
        strat_info = pool_map_full.get(code, {})
        tag = strat_info.get('tag', "持仓" if is_hold else "")
        limit_type = strat_info.get('limit_up_type', '')

        
        # Call Auction Data (Prioritize Realtime file > Pool info)
        call_info = call_auction_map.get(code, {})
        call_amt_real = call_info.get('amount', 0)
        call_pct_real = call_info.get('pct', 0)
        
        # If no realtime file data, fallback to pool (though pool usually has yesterday's or pre-calc)
        # But here we want the realtime "call_auction" data
        if not call_info:
             # Maybe pool has it? 
             # call_ratio is just a ratio, not amount.
             pass
        
        # Calculate Call Ratio dynamically if yesterday's amount is available
        last_amt = float(strat_info.get('last_amount', 0))
        if last_amt > 10000: # Valid amount
             # call_amt_real is Raw Yuan. last_amt is Raw Yuan.
             call_ratio = call_amt_real / last_amt
        else:
             # Fallback to static
             call_ratio = float(strat_info.get('call_auction_ratio', 0))

        
        # Risk / Deviation
        dev_30 = float(strat_info.get('deviation_val_30d', 0))
        dev_10 = float(strat_info.get('deviation_val_10d', 0))
        risk_level = strat_info.get('risk_level', '') # e.g. 高危
        
        name = row['名称']
        price = row['最新价']
        pct = row['涨跌幅']
        
        # 5分钟涨速
        speed5 = float(row.get('5分钟涨跌', 0))
        
        sig_level, sig_text, sig_color, bias, cost_ratio = check_signals(row, holding_info, tag, index_pct, current_time)
        
        is_manual = code in manual_map
        if is_hold or is_manual or sig_level >= 3:
            display_list.append({
                'code': code,
                'name': name,
                'price': price,
                'pct': pct,
                'speed5': speed5,
                'bias': bias,
                'cost': holding_info['cost'] if is_hold else 0,
                'tag': tag,
                'signal': sig_text,
                'color': sig_color,
                'is_hold': is_hold,
                'vr': float(row.get('量比', 0)),
                'to': float(row.get('换手率', 0)),
                # New Fields
                'call_ratio': call_ratio,
                'limit_type': limit_type,
                'dev_30': dev_30,
                'dev_10': dev_10,
                'risk_level': risk_level,
                'call_amt': call_amt_real if not pd.isna(call_amt_real) else 0.0,
                'call_pct': call_pct_real if not pd.isna(call_pct_real) else 0.0
            })

            
    # 排序
    # 头部信息
    idx_color = Fore.RED if index_pct > 0 else Fore.GREEN
    # 格式化头部信息：上证 + 量比 + 成交额 + 情绪
    header_info = f"上证: {idx_color}{index_price} ({index_pct}%) {Style.RESET_ALL} | 量比: {sh_vr} | 成交: {total_amt_str}"
    sentiment_info = f" | 高度: {highest_space}板 | 涨停: {limit_up_count} | 溢价: {prem}%"
    
    auction_info = f" | 竞价源: {call_source_info}" if call_source_info else ""
    
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 指挥室 {current_time} {Style.RESET_ALL} | {header_info}{sentiment_info}{auction_info}")

    print(f"{Fore.YELLOW}🔥 领涨: {sector_summary} | 💰 资金: {inflow_str}{Style.RESET_ALL}")
    print("-" * 135)
    print(f"{'代码':<8} {'名称':<8} {'涨幅%':<8} {'5分%':<7} {'现价':<8} {'乖离%':<7} {'成本/状态':<10} {'量比':<6} {'竞价%':<5} {'竞价额':<8} {'竞价涨%':<7} {'信号/属性'}")

    print("-" * 135)
    
    for item in display_list:
        c_pct = Fore.RED if item['pct'] > 0 else Fore.GREEN
        
        # 标记: 持仓(黄底黑字) > 手动(蓝底白字) > 普通
        c_mark = ""
        if item['is_hold']:
            c_mark = Back.YELLOW + Fore.BLACK
        elif item['code'] in manual_map:
            c_mark = Back.BLUE + Fore.WHITE
            
        code_str = f"{c_mark}{item['code']}{Style.RESET_ALL}"
        
        # 5分钟涨速颜色
        s5 = item['speed5']
        c_speed = Fore.RED if s5 > 1 else (Fore.MAGENTA if s5 > 2 else (Fore.GREEN if s5 < -1 else ""))
        
        cost_str = ""
        if item['is_hold']:
                cost_str = f"{item['cost']:.2f}"
        else:
                cost_str = "均线上" if item['bias'] > 0 else "均线下"
                     
        bias_val = item['bias']
        c_bias = Fore.MAGENTA if bias_val > 3 else (Fore.CYAN if bias_val < -3 else "")
        
        # Prepare Risk / Deviation Signals
        risk_str = ""
        if item['dev_30'] > 0: risk_str += f"⚠️30日{item['dev_30']:.0f}% "
        if item['dev_10'] > 0: risk_str += f"⚠️10日{item['dev_10']:.0f}% "
        
        # Prepare Limit Type (Show in name or separate?)
        # Combine Limit Type with Tag for display
        final_tag = item['tag']
        if item['limit_type']:
            final_tag = f"[{item['limit_type']}] " + final_tag
            
        # Highlight Call Ratio (Show as %)
        c_ratio = item['call_ratio']
        ratio_val_pct = c_ratio * 100
        ratio_str = f"{ratio_val_pct:.1f}"
        if c_ratio > 0.1: ratio_str = f"{Fore.RED}{ratio_str}{Style.RESET_ALL}"
        
        print(f"{code_str:<18} {item['name']:<9} {c_pct}{item['pct']:<9.2f}{Style.RESET_ALL} {c_speed}{item['speed5']:<8.2f}{Style.RESET_ALL} {item['price']:<9.2f} {c_bias}{item['bias']:<8.2f}{Style.RESET_ALL} {cost_str:<13} {item['vr']:<8.1f} {ratio_str:<6} {int(item['call_amt']):<8} {item['call_pct']:<8.2f} {item['color']}{item['signal']} {Style.RESET_ALL}{risk_str}{final_tag[:20]}")
        
    print("-" * 110)
    print("🚀 F-Guide: 持仓急拉卖T，急杀买T；断板及时离场。")
    print("\n📊 全行业板块涨跌幅一览:")
    print(sector_detail)

if __name__ == "__main__":
    main()
