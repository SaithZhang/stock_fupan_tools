# ==============================================================================
# 📌 F佬/Bo佬 盘中实时作战指挥室 (src/monitors/intraday_monitor.py) - 【优化版】
# v1.2 精简信号版 - 解决满屏信号问题，优化金额显示
# Last Modified: 2026-01-12
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
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import (
    load_holdings, load_pool_full, load_history_basics,
    load_manual_focus, get_latest_call_auction_file, parse_call_auction_file
)


# ================= 🛠️ 辅助函数 =================

def format_amount(num):
    """将数字转换为中文万/亿格式"""
    if not num: return "0"
    try:
        num = float(num)
        if num > 100000000:
            return f"{num / 100000000:.2f}亿"
        elif num > 10000:
            return f"{num / 10000:.0f}万"
        else:
            return str(int(num))
    except:
        return str(num)


def get_market_mood():
    """获取市场情绪：领涨板块"""
    try:
        df = ak.stock_board_industry_name_em()
        df = df.sort_values(by='涨跌幅', ascending=False)

        # 领涨前5
        top_5 = df.head(5)
        top_sectors = [f"{row['板块名称']}({row['涨跌幅']}%)" for _, row in top_5.iterrows()]
        summary = " 🔥 ".join(top_sectors)
        return summary
    except:
        return "数据获取中..."


def get_index_status():
    """获取上证指数信息"""
    info = {'price': 0.0, 'pct': 0.0, 'sh_amt': 0.0, 'sz_amt': 0.0, 'sh_vr': 0.0}
    try:
        df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        sh = df[df['名称'] == '上证指数']
        if not sh.empty:
            item = sh.iloc[0]
            info['price'] = float(item['最新价'])
            info['pct'] = float(item['涨跌幅'])
            info['sh_amt'] = float(item['成交额'])
            info['sh_vr'] = float(item.get('量比', 0))

        sz = df[df['名称'] == '深证成指']
        if not sz.empty:
            info['sz_amt'] = float(sz.iloc[0]['成交额'])
    except:
        pass
    return info


def check_signals(row, holding_info, tag, index_pct, current_time_str):
    """
    分析单只股票，生成信号 (逻辑收紧版)
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
        amt = float(row['成交额'])
        vol = float(row['成交量'])

        # 计算 VWAP (均价)
        vwap = price
        if vol > 0: vwap = amt / (vol * 100)

    except:
        return (0, "", "", 0.0, 0.0)

    signals = []

    bias = (price - vwap) / vwap * 100
    cost_ratio = (price - cost) / cost * 100 if cost > 0 else 0.0
    hour = int(current_time_str.split(':')[0])

    # 判断是否涨停 (粗略判断)
    is_limit_up = (pct > 9.8 and price < 30) or (pct > 19.8)
    # 判断是否炸板 (最高价接近涨停，但现价回落)
    is_broken = (high > open_p * 1.09) and (price < high * 0.98) and (pct > 0)

    # --- 1. 状态定义 (Status) ---
    if is_limit_up:
        signals.append((10, "🚀涨停封板", Fore.MAGENTA))
    elif is_broken:
        signals.append((9, "⚠️炸板回落", Fore.YELLOW))

    # --- 2. 持仓股策略 (Holding) ---
    if is_holding:
        if bias > 4.0 and not is_limit_up: signals.append((8, "🚀急拉卖T", Fore.MAGENTA))
        if bias < -3.0 and index_pct > -0.5: signals.append((8, "🌊急杀买T", Fore.CYAN))
        if pct < -4.0 and cost_ratio < -2.0: signals.append((7, "⚠️止损提醒", Fore.RED))

    # --- 3. 策略池信号 (Strategy) ---
    else:
        # A. 弱转强 (条件收紧：涨幅>3%，量比>1.2，且当前价高于均价)
        # 避免大盘普涨时满屏都是信号
        if open_p < vwap and price > vwap and pct > 3.0 and vr > 1.2 and not is_limit_up:
            signals.append((6, "★弱转强", Fore.RED))

        # B. 均线承接 (缩量回调到均线)
        if abs(bias) < 0.3 and pct > 0 and pct < 5.0 and vr < 0.9:
            signals.append((4, "👀缩量稳住", Fore.WHITE))

        # C. 人气扫板 (接近涨停)
        if pct > 8.0 and not is_limit_up:
            signals.append((7, "🔥人气扫板", Fore.RED))

        # D. 放量异动
        if vr > 2.5 and pct > 4.0 and pct < 8.0:
            signals.append((5, "📈放量拉升", Fore.YELLOW))

    if not signals: return (0, "观察", Fore.WHITE, bias, cost_ratio)
    signals.sort(key=lambda x: x[0], reverse=True)

    return (signals[0][0], signals[0][1], signals[0][2], bias, cost_ratio)


def load_call_auction_data():
    """读取最新的竞价数据"""
    file_path = get_latest_call_auction_file()
    if not file_path: return {}, ""

    mod_time = os.path.getmtime(file_path)
    time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%H:%M:%S')
    filename = os.path.basename(file_path)

    try:
        # 使用 shared utility 解析
        df = parse_call_auction_file(file_path)
        if df is None or df.empty: return {}, f"{filename} (Empty)"

        data_map = {}
        for _, row in df.iterrows():
            code = row['code']
            amt_wan = row['auc_amt']  # 解析器返回的是万
            pct = row['open_pct']
            # 这里存 raw value，方便后面处理
            data_map[code] = {'amount': amt_wan * 10000, 'pct': pct}

        return data_map, f"{filename} ({time_str})"
    except Exception as e:
        return {}, f"Error: {str(e)}"


# ================= 🚀 主程序 =================

def main():
    print(f"\n{Back.RED}{Fore.WHITE} F佬 · 作战指挥室 (实时监控) v1.2 {Style.RESET_ALL}")

    # 1. 加载数据
    holdings = load_holdings()
    pool_map_full = load_pool_full()
    manual_map = load_manual_focus()
    call_auction_map, call_source_info = load_call_auction_data()

    # 2. 确定监控名单
    monitor_codes = set(holdings) | set(pool_map_full.keys()) | set(manual_map.keys())
    monitor_list = list(monitor_codes)

    print(f"🎯 监控目标: {len(monitor_list)} 只 (持仓 {len(holdings)} | 策略 {len(pool_map_full)})")

    # 3. 获取实时行情
    try:
        df = ak.stock_zh_a_spot_em()
    except:
        print("⚠️ 无法连接行情服务器")
        return

    # 4. 获取环境数据
    idx_info = get_index_status()
    total_amt = idx_info['sh_amt'] + idx_info['sz_amt']
    total_amt_str = f"{total_amt / 1000000000000:.2f}万亿" if total_amt > 1000000000000 else f"{total_amt / 100000000:.0f}亿"
    sector_summary = get_market_mood()
    current_time = datetime.datetime.now().strftime('%H:%M:%S')

    # 5. 筛选与计算
    df_target = df[df['代码'].isin(monitor_list)].copy()
    display_list = []

    for _, row in df_target.iterrows():
        code = row['代码']
        name = row['名称']
        price = float(row['最新价'])
        pct = float(row['涨跌幅'])
        speed5 = float(row.get('5分钟涨跌', 0))

        # 关联信息
        holding_info = holdings.get(code)
        is_hold = holding_info is not None
        strat_info = pool_map_full.get(code, {})
        tag = strat_info.get('tag', "")

        # 竞价数据
        call_info = call_auction_map.get(code, {})
        call_amt = call_info.get('amount', 0)
        call_pct = call_info.get('pct', 0)

        # 信号检测
        sig_level, sig_text, sig_color, bias, cost_ratio = check_signals(row, holding_info, tag, idx_info['pct'],
                                                                         current_time)

        # 筛选显示条件：持仓 OR 手动关注 OR 有重要信号(Level>=5) OR 竞价爆量
        show_it = is_hold or (code in manual_map) or (sig_level >= 5)

        # 修正：如果是满屏涨停的日子，只显示没涨停的或者特殊的
        if sig_text == "🚀涨停封板" and not (is_hold or code in manual_map):
            # 涨停股如果不在特别关注里，为了防刷屏，可以根据需求屏蔽，或者保留
            pass

        if show_it:
            display_list.append({
                'code': code, 'name': name, 'price': price, 'pct': pct, 'speed5': speed5,
                'bias': bias, 'sig_text': sig_text, 'sig_color': sig_color,
                'is_hold': is_hold, 'is_manual': code in manual_map,
                'vr': float(row.get('量比', 0)),
                'call_amt': call_amt, 'call_pct': call_pct,
                'tag': tag
            })

    # 6. 排序 (持仓在前，然后按涨幅)
    display_list.sort(key=lambda x: (not x['is_hold'], not x['is_manual'], -x['pct']))

    # 7. 打印输出
    idx_color = Fore.RED if idx_info['pct'] > 0 else Fore.GREEN
    header = f"上证: {idx_color}{idx_info['price']} ({idx_info['pct']}%) {Style.RESET_ALL} | 量比: {idx_info['sh_vr']} | 成交: {total_amt_str}"
    print(f"\n{Back.BLUE}{Fore.WHITE} {current_time} {Style.RESET_ALL} | {header} | 竞价源: {call_source_info}")
    print(f"{Fore.YELLOW}🔥 领涨: {sector_summary}{Style.RESET_ALL}")

    print("-" * 120)
    # 调整了列宽
    print(
        f"{'代码':<7} {'名称':<8} {'涨幅%':<7} {'现价':<7} {'乖离%':<6} {'量比':<5} {'竞价额':<8} {'竞价%':<6} {'信号'}")
    print("-" * 120)

    for item in display_list:
        # 颜色处理
        c_pct = Fore.RED if item['pct'] > 0 else Fore.GREEN
        c_code = Back.YELLOW + Fore.BLACK if item['is_hold'] else (Back.BLUE + Fore.WHITE if item['is_manual'] else "")

        # 格式化数据
        name_disp = item['name'][:4]  # 截断名字防对齐乱
        # 使用 format_amount 优化竞价额显示
        amt_str = format_amount(item['call_amt'])

        # 建议修改为（放宽到 20 字符）：
        tag_str = item['tag'].replace('★人气', '').replace('成交', '').strip()[:20]

        row_str = (
            f"{c_code}{item['code']}{Style.RESET_ALL:<0} "
            f"{item['name']:<8} "
            f"{c_pct}{item['pct']:>6.2f}{Style.RESET_ALL} "
            f"{item['price']:>7.2f} "
            f"{item['bias']:>6.1f} "
            f"{item['vr']:>5.1f} "
            f"{amt_str:<8} "
            f"{item['call_pct']:>5.2f}  "
            f"{item['sig_color']}{item['sig_text']:<6}{Style.RESET_ALL} "
            f"{Fore.CYAN}{tag_str}{Style.RESET_ALL}"
        )
        print(row_str)

    print("-" * 120)


if __name__ == "__main__":
    main()