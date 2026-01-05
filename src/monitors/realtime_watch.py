# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py) - v2.3.1 修复Bug版
# ==============================================================================
# 更新日志:
# v2.3.1: 修复 NameError: 'active_pool' 未定义错误；恢复数据清洗合并逻辑。
# v2.3: 修复"炸板"误判bug，自动识别 10cm/20cm/30cm 涨停阈值。
# v2.2: 全景监控。
# ==============================================================================

import requests
import pandas as pd
import time
import os
import datetime
import threading
import akshare as ak
from colorama import init, Fore, Style, Back
import re
import sys

# 适配 Windows 控制台编码
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
CSV_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')

print(f"{Fore.CYAN}🔧 监控数据源定位: {CSV_PATH}{Fore.RESET}")

# ================= 🛡️ 风控配置 =================
MARKET_LEADER_CODE = "sh603278"  # 示例：大业
INDEX_CODE = "sh000001"  # 上证指数
HOT_TOPICS = ["机器人", "航天", "AI", "消费电子", "算力", "低空", "固态", "军工", "卫星", "脑机"]
MARKET_BREADTH = {'up': 0, 'down': 0, 'flat': 0, 'update_time': '-'}


# ================= 🛠️ 数据加载函数 =================

def load_holdings_direct():
    """直接读取持仓文件"""
    if not os.path.exists(HOLDINGS_PATH): return pd.DataFrame()
    new_rows = []
    try:
        with open(HOLDINGS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or "证券代码" in line or "合计" in line: continue
            parts = re.split(r'\s+', line)
            if len(parts) < 2: continue
            code = parts[0]
            name = parts[1]
            if not code.isdigit() or len(code) != 6: continue
            sina_code = f"sz{code}" if code.startswith(('0', '3')) else f"sh{code}"
            new_rows.append({
                'sina_code': sina_code, 'name': name, 'tag': f"持仓/{name}", 'vol': 0, 'code': code, 'link_dragon': ''
            })
    except:
        pass
    return pd.DataFrame(new_rows)


def load_ths_clipboard_to_df():
    """读取同花顺剪贴板"""
    if not os.path.exists(THS_PATH): return pd.DataFrame()
    lines = []
    try:
        with open(THS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(THS_PATH, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except:
            return pd.DataFrame()
    new_rows = []
    for line in lines:
        line = line.strip()
        if not line or "代码" in line: continue
        parts = re.split(r'\s+', line)
        if len(parts) < 2: continue
        raw_code = parts[0]
        name = parts[1]
        sina_code = raw_code.lower()
        pure_code = re.sub(r'\D', '', raw_code)
        if len(pure_code) != 6: continue
        new_rows.append({
            'sina_code': sina_code, 'name': name, 'tag': f"同花顺/{name}", 'vol': 0, 'code': pure_code,
            'link_dragon': ''
        })
    return pd.DataFrame(new_rows)


def load_strategy_pool():
    """加载并合并所有策略池"""
    df_main = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df_main = pd.read_csv(CSV_PATH, dtype={'code': str, 'sina_code': str})
        except:
            pass
    df_holdings = load_holdings_direct()
    df_ths = load_ths_clipboard_to_df()

    combined_list = []
    seen_codes = set()
    # 优先级：持仓 > 策略CSV > 剪贴板
    for df in [df_holdings, df_main, df_ths]:
        if not df.empty:
            for _, row in df.iterrows():
                if row['code'] not in seen_codes:
                    combined_list.append(row.to_dict())
                    seen_codes.add(row['code'])
    df_final = pd.DataFrame(combined_list)
    if not df_final.empty:
        if 'link_dragon' not in df_final.columns: df_final['link_dragon'] = ""
        df_final['link_dragon'] = df_final['link_dragon'].fillna('')
        if 'sina_code' not in df_final.columns:
            df_final['sina_code'] = df_final['code'].apply(
                lambda x: f"sz{x}" if str(x).startswith(('0', '3')) else f"sh{x}")
        return df_final.to_dict('records')
    return []


# ================= 📊 核心监控逻辑 =================

def fetch_sina_data(sina_codes):
    """从新浪接口批量获取行情"""
    if not sina_codes: return {}
    query_list = sina_codes + [INDEX_CODE]
    chunk_size = 80
    parsed_data = {}
    for i in range(0, len(query_list), chunk_size):
        chunk = query_list[i:i + chunk_size]
        url = f"http://hq.sinajs.cn/list={','.join(chunk)}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        try:
            resp = requests.get(url, headers=headers, timeout=2)
            resp.encoding = 'gbk'
            for line in resp.text.strip().split('\n'):
                if not line: continue
                parts = line.split('=')
                if len(parts) < 2: continue

                code = parts[0].split('_')[-1]
                val = parts[1].strip('"')
                if not val: continue
                d = val.split(',')
                if len(d) < 10: continue

                open_p = float(d[1])
                pre_c = float(d[2])
                curr_p = float(d[3])
                high_p = float(d[4])

                # 竞价或停牌处理
                if curr_p == 0: curr_p = open_p if open_p > 0 else pre_c
                if pre_c == 0: continue

                pct = (curr_p - pre_c) / pre_c * 100
                open_pct = (open_p - pre_c) / pre_c * 100 if open_p > 0 else 0
                max_pct = (high_p - pre_c) / pre_c * 100
                amt = float(d[9]) / 100000000

                parsed_data[code] = {
                    'curr_p': curr_p, 'pre_c': pre_c, 'pct': pct,
                    'open_pct': open_pct, 'max_pct': max_pct, 'vol': int(d[8]) // 100, 'amt': amt
                }
        except:
            pass
    return parsed_data


def update_market_breadth():
    """后台线程：更新全市场涨跌家数"""
    global MARKET_BREADTH
    while True:
        try:
            # akshare 有时会打印进度条，这里不屏蔽也没事，因为在后台线程
            df = ak.stock_zh_a_spot_em()
            if not df.empty:
                MARKET_BREADTH = {
                    'up': len(df[df['涨跌幅'] > 0]), 'down': len(df[df['涨跌幅'] < 0]),
                    'flat': len(df[df['涨跌幅'] == 0]), 'update_time': datetime.datetime.now().strftime("%H:%M")
                }
        except:
            # 接口报错暂不处理，保持旧数据
            pass
        # 每60秒更新一次
        time.sleep(60)


# ================= 🧠 AI 决策核心 (v2.3 修复版) =================

def get_limit_threshold(code, name):
    """🔥 核心修复：精准判断涨停板阈值"""
    # 1. ST股 (5%)
    if 'ST' in name:
        return 4.9

    # 2. 北交所 (30%) - 8/4开头
    if code.startswith('bj') or code.startswith('8') or code.startswith('4'):
        return 29.5

    # 3. 科创/创业 (20%) - 688/300/301开头
    if 'sh68' in code or 'sz3' in code:
        return 19.5

    # 4. 主板 (10%)
    return 9.85


def get_smart_decision(item, real_time_data, sentiment_ok, market_status):
    code = item['sina_code']
    name = item.get('name', '')
    if code not in real_time_data: return ""
    data = real_time_data[code]
    pct = data['pct']
    open_pct = data['open_pct']
    curr_p = data['curr_p']
    max_pct = data['max_pct']
    tag = str(item.get('tag', ''))

    limit_cap = get_limit_threshold(code, name)

    yesterday_v = float(item.get('yesterday_vol', 0))
    today_v = float(item.get('vol', 0))
    vol_ratio = (today_v / yesterday_v * 100) if yesterday_v > 0 else 0
    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    # 1. 环境否决
    is_market_crash = (market_status['pct'] < -1.0 and MARKET_BREADTH['down'] > 3500)
    if not sentiment_ok or is_market_crash:
        if "持仓" in tag:
            return f"{Fore.YELLOW}🛡️防守观察{Style.RESET_ALL}"
        else:
            return f"{Back.RED}{Fore.WHITE}⛔空仓(环境差){Style.RESET_ALL}"

    # 2. 状态判断 (精准版)
    is_hard_board = (pct >= limit_cap)
    is_touched_limit = (max_pct >= limit_cap)
    is_broken_board = (is_touched_limit and pct < limit_cap - 0.5)
    is_diving = (max_pct > 6.0 and pct < max_pct - 3.0 and not is_touched_limit)

    if is_hard_board: return f"{Fore.RED}🔒锁仓{Style.RESET_ALL}"
    if is_broken_board: return f"{Fore.YELLOW}💥炸板离场{Style.RESET_ALL}"
    if is_diving: return f"{Fore.BLUE}📉冲高回落{Style.RESET_ALL}"

    # 3. 影子股过滤
    if ("参股" in tag or "影子" in tag) and open_pct > 3.0:
        return f"{Fore.CYAN}⚠️影子谨防兑现{Style.RESET_ALL}"

    # 4. 时间锁
    if now_str < "09:30:00":
        if 4.0 <= open_pct <= 7.5:
            return f"{Fore.YELLOW}👀尴尬区(防骗){Style.RESET_ALL}"
        elif vol_ratio > 5 and open_pct > 0:
            return f"{Fore.MAGENTA}👻竞价抢筹{Style.RESET_ALL}"
        else:
            return "观察"

    # 5. 机会判断
    pre_weak = any(x in tag for x in ['烂', '炸', '跌', '弱'])
    is_confirmed = (curr_p >= data['pre_c'] * (1 + open_pct / 100))
    if pre_weak and open_pct > 1.0:
        if is_confirmed:
            return f"{Back.RED}{Fore.WHITE}🔥弱转强(确认){Style.RESET_ALL}"
        else:
            return f"{Fore.GREEN}❌低走(骗炮){Style.RESET_ALL}"

    if '跌' in tag and pct > 0: return f"{Fore.MAGENTA}🔥反核拉升{Style.RESET_ALL}"
    if vol_ratio > 10 and pct > 1.0: return f"{Fore.CYAN}放量上攻{Style.RESET_ALL}"

    return "观察"


# ================= 🔄 监控循环 =================

def monitor_loop(pool):
    # 1. 提取所有需要查询的代码
    all_codes = set()
    for item in pool:
        if 'sina_code' in item: all_codes.add(item['sina_code'])
        if item['link_dragon']: all_codes.add(item['link_dragon'])

    # 2. 获取实时行情
    real_time_data = fetch_sina_data(list(all_codes))
    if not real_time_data: return

    # 🔥 FIX START: 组装 active_pool (v2.3 缺失部分) 🔥
    active_pool = []
    for item in pool:
        code = item.get('sina_code')
        if code in real_time_data:
            # 浅拷贝，防止无限追加
            new_item = item.copy()

            # 核心逻辑：CSV里的是"昨日量"(vol)，新浪接口给的是"今日量"(vol)
            # 必须先保存昨日量，再更新今日数据
            new_item['yesterday_vol'] = item.get('vol', 0)

            # 更新实时数据
            new_item.update(real_time_data[code])
            active_pool.append(new_item)
    # 🔥 FIX END 🔥

    # 3. 市场情绪判断
    sentiment_ok = True
    leader_info = "未知"
    market_info = {'pct': 0}

    if MARKET_LEADER_CODE in real_time_data:
        ldr = real_time_data[MARKET_LEADER_CODE]
        if ldr['pct'] < -7.0:
            sentiment_ok = False
            leader_info = f"{Back.GREEN}{Fore.WHITE} 大业跌停 {Style.RESET_ALL}"
        else:
            leader_info = f"大业({ldr['pct']:.1f}%)"

    idx_disp = "连接中..."
    if INDEX_CODE in real_time_data:
        idx = real_time_data[INDEX_CODE]
        market_info['pct'] = idx['pct']
        idx_color = Fore.RED if idx['pct'] > 0 else Fore.GREEN
        idx_disp = f"{idx_color}上证: {idx['curr_p']:.0f} ({idx['pct']:.2f}%){Style.RESET_ALL}"
        if idx['pct'] > 0 and MARKET_BREADTH['down'] > MARKET_BREADTH['up']:
            idx_disp += f" {Back.YELLOW}{Fore.BLACK}⚠️指数失真{Style.RESET_ALL}"

    up_cnt = MARKET_BREADTH['up']
    down_cnt = MARKET_BREADTH['down']
    breadth_disp = f"{Fore.RED}↑{up_cnt}{Style.RESET_ALL} : {Fore.GREEN}↓{down_cnt}{Style.RESET_ALL}"

    # 4. 打印面板
    os.system('cls' if os.name == 'nt' else 'clear')
    curr_time = time.strftime('%H:%M:%S')
    print("=" * 145)
    print(f"🚀 F佬全景驾驶舱 v2.3.1 | {curr_time} | {idx_disp} | 市场: {breadth_disp} | 龙头: {leader_info}")
    print("=" * 145)
    print(
        f"{'名称':<8} {'标签':<25} {'涨幅':<12} {'现价':<8} {'今开%':<8} {'联动':<15} {'最高%':<8} {'量比':<10} {'AI智能决策'}")
    print("-" * 145)

    # 5. 遍历组装好的 active_pool
    for item in active_pool:
        name = item.get('name', '-')[:4]
        tag = item.get('tag', '-')
        pct = item['pct']
        open_pct = item['open_pct']
        link_dragon = item.get('link_dragon')

        link_str = "-"
        if link_dragon and link_dragon in real_time_data:
            d_pct = real_time_data[link_dragon]['pct']
            if d_pct > 9.5:
                link_str = f"{Fore.RED}大哥涨停{Style.RESET_ALL}"
            elif d_pct < -5:
                link_str = f"{Fore.GREEN}大哥大跌{Style.RESET_ALL}"

        hit_topics = sum(1 for t in HOT_TOPICS if t in str(tag))
        tag_disp = str(tag)[:22]
        if hit_topics >= 2 or "持仓" in str(tag):
            tag_disp = f"{Fore.MAGENTA}{tag_disp:<25}{Style.RESET_ALL}"
        else:
            tag_disp = f"{tag_disp:<25}"

        pct_str = f"{pct:+.2f}%"
        if pct > 9.8:
            pct_str = f"{Fore.RED}🚀{pct_str}{Style.RESET_ALL}"
        elif pct < -9.0:
            pct_str = f"{Fore.GREEN}🤮{pct_str}{Style.RESET_ALL}"
        elif pct > 0:
            pct_str = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
        else:
            pct_str = f"{Fore.GREEN}{pct_str}{Style.RESET_ALL}"

        open_str = f"{open_pct:+.1f}%"
        if open_pct > 0:
            open_str = f"{Fore.RED}{open_str}{Style.RESET_ALL}"
        else:
            open_str = f"{Fore.GREEN}{open_str}{Style.RESET_ALL}"

        # 量比计算：确保 yesterday_vol 存在
        y_v = float(item.get('yesterday_vol', 1))
        t_v = float(item.get('vol', 0))
        ratio = (t_v / y_v * 100) if y_v > 0 else 0
        ratio_str = f"{ratio:.1f}%"
        if ratio > 5: ratio_str = f"{Fore.YELLOW}{ratio_str}{Style.RESET_ALL}"

        decision = get_smart_decision(item, real_time_data, sentiment_ok, market_info)
        print(
            f"{name:<8} {tag_disp} {pct_str:<22} {item['curr_p']:<8} {open_str:<18} {link_str:<24} {item['max_pct']:<8.1f} {ratio_str:<10} {decision}")

    print("=" * 145)


if __name__ == "__main__":
    t = threading.Thread(target=update_market_breadth, daemon=True)
    t.start()

    print(f"{Fore.CYAN}正在加载策略池...{Style.RESET_ALL}")
    pool = load_strategy_pool()

    if pool:
        print(f"监控启动: {len(pool)} 只标的 (按 Ctrl+C 退出)...")
        try:
            while True:
                monitor_loop(pool)
                time.sleep(3)
        except KeyboardInterrupt:
            print("\n退出")
    else:
        print("无数据，请检查 strategy_pool.csv 或 ths_clipboard.txt")