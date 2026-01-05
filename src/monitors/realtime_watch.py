# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py) - v3.2.1 语法修复版
# ==============================================================================
import requests
import pandas as pd
import time
import os
import json
import re
import sys
from colorama import init, Fore, Style, Back

# 适配 Windows 控制台
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
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'db', 'stock_concepts.json')

# 重点关注概念 (高亮词库)
HOT_TOPICS = ["机器人", "航天", "AI", "消费电子", "算力", "低空", "固态", "军工", "卫星", "脑机", "信创", "华为",
              "海思", "自主可控", "西部大开发", "蛇"]


# ================= 🧠 AI 智能决策核心 =================

def get_stock_limit(code):
    """判断涨跌停阈值 (10cm/20cm/30cm)"""
    if code.startswith('8') or code.startswith('4'): return 29.8  # 北交所 30cm
    if code.startswith('3') or code.startswith('68'): return 19.8  # 创业板/科创板 20cm
    return 9.8  # 主板 10cm


def get_smart_decision(item):
    """
    🔥 F佬核心交易策略逻辑
    """
    pct = item['pct']  # 当前涨幅
    max_pct = item['max_pct']  # 最高涨幅
    open_pct = item['open_pct']  # 开盘涨幅
    vol_ratio = item.get('vol_ratio', 0)  # 量比
    code = str(item.get('code', ''))

    limit = get_stock_limit(code)  # 获取涨停阈值

    # 1. 🔒 涨停/连板
    if pct >= limit:
        if open_pct >= limit - 0.5:
            return f"{Back.RED}{Fore.WHITE}🔒一字板{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}🔒涨停封板{Style.RESET_ALL}"

    # 2. 🤢 核按钮/跌停
    if pct <= -limit:
        return f"{Back.GREEN}{Fore.WHITE}🤢跌停死锁{Style.RESET_ALL}"
    if pct < -8.0:
        return f"{Fore.GREEN}🤢核按钮{Style.RESET_ALL}"

    # 3. 💥 炸板 (摸过涨停，现在没封住)
    if max_pct >= limit and pct < limit - 1.0:
        return f"{Fore.YELLOW}💥炸板离场{Style.RESET_ALL}"

    # 4. 🔥 弱转强 (最核心模式：开盘不高，盘中爆量拉升)
    # 逻辑：开盘在5个点以下，当前涨幅大于5个点，且量比放大
    if open_pct < 4.0 and pct > 6.0 and vol_ratio > 80:
        return f"{Fore.MAGENTA}🔥弱转强{Style.RESET_ALL}"

    # 5. 🚀 地天板/深水拉升 (博弈大长腿)
    if open_pct < -3.0 and pct > 3.0:
        return f"{Fore.RED}🚀深水拉升{Style.RESET_ALL}"

    # 6. 📉 冲高回落 (也是卖点)
    if max_pct - pct > 4.0 and pct > 0:
        return f"{Fore.CYAN}📉冲高回落{Style.RESET_ALL}"

    # 7. 📦 低位潜伏 (跌幅不大，也没大涨，但量能有异动)
    if -2 < pct < 3 and vol_ratio > 150:
        return f"{Fore.BLUE}📦放量异动{Style.RESET_ALL}"

    # 8. 🧟 骗炮 (大幅高开低走)
    if open_pct > 3.0 and pct < 0:
        return f"{Fore.GREEN}🧟高开骗炮{Style.RESET_ALL}"

    return "💤观察"


# ================= 🛠️ 数据加载模块 =================

def load_concept_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def load_strategy_pool(concept_db):
    # 1. 读CSV
    df_main = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df_main = pd.read_csv(CSV_PATH, dtype={'code': str, 'sina_code': str})
        except:
            pass

    # 2. 读剪贴板
    rows = []
    if os.path.exists(THS_PATH):
        lines = []
        try:
            with open(THS_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except:
            try:
                # 修复了这里的缩进错误
                with open(THS_PATH, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            except:
                lines = []

        for line in lines:
            line = line.strip()
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                raw_code = parts[0]
                pure_code = re.sub(r'\D', '', raw_code)
                if len(pure_code) == 6:
                    sina = f"sz{pure_code}" if pure_code.startswith(('0', '3')) else f"sh{pure_code}"
                    rows.append(
                        {'code': pure_code, 'name': parts[1], 'sina_code': sina, 'vol': 0, 'tag': '同花顺/临时'})

    df_ths = pd.DataFrame(rows)

    # 3. 合并
    if not df_ths.empty:
        if not df_main.empty:
            existing = set(df_main['code'].astype(str).tolist())
            df_ths = df_ths[~df_ths['code'].isin(existing)]
            df_final = pd.concat([df_main, df_ths], ignore_index=True)
        else:
            df_final = df_ths
    else:
        df_final = df_main

    if df_final.empty: return []

    # 4. 注入概念
    pool_list = df_final.to_dict('records')
    for item in pool_list:
        code = str(item.get('code'))
        origin_tag = str(item.get('tag', ''))
        display_tag = origin_tag
        if code in concept_db:
            db_concepts = concept_db[code]
            if "同花顺" in origin_tag or origin_tag == "nan" or not origin_tag:
                display_tag = db_concepts
            else:
                industry_only = db_concepts.split('|')[0].strip()
                display_tag = f"{origin_tag} ({industry_only})"
        item['tag_display'] = display_tag

    return pool_list


# ================= 📊 行情监控模块 =================

def fetch_sina_data(sina_codes):
    if not sina_codes: return {}
    parsed = {}
    chunk_size = 80
    for i in range(0, len(sina_codes), chunk_size):
        chunk = sina_codes[i:i + chunk_size]
        try:
            url = f"http://hq.sinajs.cn/list={','.join(chunk)}"
            resp = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn'}, timeout=2)
            for line in resp.text.strip().split('\n'):
                if not line: continue
                parts = line.split('=')
                if len(parts) < 2: continue
                code = parts[0].split('_')[-1]
                val = parts[1].strip('"')
                if not val: continue
                data = val.split(',')
                if len(data) < 30: continue

                curr = float(data[3])
                pre = float(data[2])
                if pre == 0: continue
                if curr == 0: curr = pre

                parsed[code] = {
                    'curr_p': curr,
                    'pct': (curr - pre) / pre * 100,
                    'open_pct': (float(data[1]) - pre) / pre * 100 if float(data[1]) > 0 else 0,
                    'max_pct': (float(data[4]) - pre) / pre * 100,
                    'vol': float(data[8]) / 100
                }
        except:
            pass
    return parsed


def monitor_loop(pool):
    all_codes = [p.get('sina_code') for p in pool if p.get('sina_code')]
    real_time = fetch_sina_data(all_codes)

    active_pool = []
    up_count = 0

    for item in pool:
        code = item.get('sina_code')
        if code in real_time:
            data = real_time[code]
            new_item = item.copy()
            new_item.update(data)

            # 量比逻辑
            y_vol = float(item.get('vol', 0))
            if y_vol > 0:
                new_item['vol_ratio'] = (new_item['vol'] / y_vol) * 100
            else:
                new_item['vol_ratio'] = 0  # 没有昨日量数据，暂为0

            if data['pct'] > 0: up_count += 1

            # 🔥 计算AI决策
            new_item['decision'] = get_smart_decision(new_item)

            active_pool.append(new_item)

    # 排序：优先看涨停 -> 其次看涨幅
    active_pool.sort(key=lambda x: x['pct'], reverse=True)

    os.system('cls' if os.name == 'nt' else 'clear')
    curr_time = time.strftime('%H:%M:%S')

    print("=" * 145)
    print(
        f"🚀 F佬全景驾驶舱 v3.2 (AI战法版) | {curr_time} | 监控: {len(active_pool)} | 🔴:{up_count} 🟢:{len(active_pool) - up_count}")
    print("=" * 145)
    print(
        f"{'名称':<8} {'核心题材 / 策略逻辑':<48} {'涨幅':<10} {'现价':<8} {'今开%':<8} {'量比%':<8} {'最高%':<8} {'AI智能决策'}")
    print("-" * 145)

    for item in active_pool:
        name = item.get('name', '-')[:4]
        tag = str(item.get('tag_display', '-'))
        tag_short = tag[:45] + ".." if len(tag) > 48 else tag

        # 高亮题材
        if any(t in tag for t in HOT_TOPICS):
            tag_disp = f"{Fore.MAGENTA}{tag_short:<48}{Style.RESET_ALL}"
        else:
            tag_disp = f"{tag_short:<48}"

        # 涨幅颜色
        pct = item['pct']
        pct_str = f"{pct:+.2f}%"
        if pct > 9.8:
            pct_str = f"{Back.RED}{Fore.WHITE}{pct_str}{Style.RESET_ALL}"
        elif pct > 0:
            pct_str = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
        else:
            pct_str = f"{Fore.GREEN}{pct_str}{Style.RESET_ALL}"

        # 决策显示
        decision = item['decision']

        print(
            f"{name:<8} {tag_disp} {pct_str:<22} {item['curr_p']:<8} {item['open_pct']:<8.1f} {item['vol_ratio']:<8.0f} {item['max_pct']:<8.1f} {decision}")

    print("=" * 145)


if __name__ == "__main__":
    print(f"{Fore.CYAN}正在初始化战法引擎...{Fore.RESET}")
    concept_db = load_concept_db()
    print(f"✅ 已装载概念库: {len(concept_db)} 条")
    pool = load_strategy_pool(concept_db)

    try:
        while True:
            monitor_loop(pool)
            time.sleep(3)
            # 每分钟盘中更新策略池
            if int(time.time()) % 60 < 3:
                new_pool = load_strategy_pool(concept_db)
                if len(new_pool) >= len(pool): pool = new_pool
    except KeyboardInterrupt:
        print("\n交易结束。")