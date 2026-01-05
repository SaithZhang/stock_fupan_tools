# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py) - v3.1 同花顺概念增强版
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
# 🔥 新增：概念数据库路径
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'db', 'stock_concepts.json')

# 重点关注概念 (高亮词库)
HOT_TOPICS = ["机器人", "航天", "AI", "消费电子", "算力", "低空", "固态", "军工", "卫星", "脑机", "信创", "华为",
              "海思", "自主可控", "西部大开发"]


# ================= 🛠️ 数据加载模块 =================

def load_concept_db():
    """加载本地概念JSON库"""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def load_strategy_pool(concept_db):
    """加载策略池并融合概念"""
    # 1. 读取 CSV 策略池
    df_main = pd.DataFrame()
    if os.path.exists(CSV_PATH):
        try:
            df_main = pd.read_csv(CSV_PATH, dtype={'code': str, 'sina_code': str})
        except:
            pass

    # 2. 读取同花顺剪贴板
    rows = []
    if os.path.exists(THS_PATH):
        try:
            with open(THS_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except:
            try:
                with open(THS_PATH, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            except:
                lines = []

        for line in lines:
            line = line.strip()
            # 简单正则匹配代码
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                raw_code = parts[0]
                name = parts[1]
                # 提取纯数字代码
                pure_code = re.sub(r'\D', '', raw_code)
                if len(pure_code) == 6:
                    sina = f"sz{pure_code}" if pure_code.startswith(('0', '3')) else f"sh{pure_code}"
                    rows.append({
                        'code': pure_code,
                        'name': name,
                        'sina_code': sina,
                        'vol': 0,
                        'tag': '同花顺/临时'  # 默认标签
                    })

    df_ths = pd.DataFrame(rows)

    # 3. 合并数据 (去重)
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

    # 4. 🔥 核心逻辑：注入概念 🔥
    pool_list = df_final.to_dict('records')
    for item in pool_list:
        code = str(item.get('code'))
        origin_tag = str(item.get('tag', ''))

        # 默认显示名
        display_tag = origin_tag

        # 如果数据库里有这个票的概念
        if code in concept_db:
            db_concepts = concept_db[code]  # 例如 "消费电子 | 华为/无线耳机"

            # 情况A: 这是一个同花顺临时票，或者原标签没啥营养 -> 直接用数据库的
            if "同花顺" in origin_tag or origin_tag == "nan" or not origin_tag:
                display_tag = db_concepts

            # 情况B: 这是一个策略票(有比如"炸板/反包"这种逻辑) -> 保留逻辑，追加行业
            else:
                # 提取行业部分 (通常在竖线前)
                industry_only = db_concepts.split('|')[0].strip()
                display_tag = f"{origin_tag} ({industry_only})"

        item['tag_display'] = display_tag

    return pool_list


# ================= 📊 行情监控模块 =================

def fetch_sina_data(sina_codes):
    """获取实时行情"""
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
                if len(data) < 30: continue  # 确保数据完整

                curr = float(data[3])
                pre = float(data[2])
                open_p = float(data[1])
                high = float(data[4])

                if pre == 0: continue
                if curr == 0: curr = pre  # 停牌或竞价未开

                parsed[code] = {
                    'curr_p': curr,
                    'pct': (curr - pre) / pre * 100,
                    'open_pct': (open_p - pre) / pre * 100 if open_p > 0 else 0,
                    'max_pct': (high - pre) / pre * 100,
                    'vol': float(data[8]) / 100  # 手
                }
        except:
            pass
    return parsed


def monitor_loop(pool):
    # 1. 获取行情
    all_codes = [p.get('sina_code') for p in pool if p.get('sina_code')]
    real_time = fetch_sina_data(all_codes)

    active_pool = []
    market_up = 0

    for item in pool:
        code = item.get('sina_code')
        if code in real_time:
            data = real_time[code]
            new_item = item.copy()
            new_item.update(data)

            # 量比
            y_vol = float(item.get('vol', 0))  # 昨日量(来自CSV)
            if y_vol > 0:
                new_item['vol_ratio'] = (new_item['vol'] / y_vol) * 100
            else:
                new_item['vol_ratio'] = 0

            if data['pct'] > 0: market_up += 1
            active_pool.append(new_item)

    # 2. 排序 (涨幅降序)
    active_pool.sort(key=lambda x: x['pct'], reverse=True)

    # 3. 渲染界面
    os.system('cls' if os.name == 'nt' else 'clear')
    curr_time = time.strftime('%H:%M:%S')

    print("=" * 140)
    print(f"🚀 F佬全景驾驶舱 v3.1 | {curr_time} | 监控: {len(active_pool)}只 | 🔴上涨: {market_up}")
    print("=" * 140)
    # 调整了列宽以适应长概念
    print(
        f"{'名称':<8} {'核心题材 / 策略逻辑':<50} {'涨幅':<10} {'现价':<8} {'今开%':<8} {'量比%':<8} {'最高%':<8} {'状态'}")
    print("-" * 140)

    for item in active_pool:
        name = item.get('name', '-')[:4]
        tag = str(item.get('tag_display', '-'))

        # 截断过长的标签
        tag_short = tag[:48] + ".." if len(tag) > 50 else tag

        # 高亮热点词
        hit_hot = any(t in tag for t in HOT_TOPICS)
        if hit_hot:
            tag_display = f"{Fore.MAGENTA}{tag_short:<50}{Style.RESET_ALL}"
        else:
            tag_display = f"{tag_short:<50}"

        # 涨跌幅颜色
        pct = item['pct']
        pct_str = f"{pct:+.2f}%"
        if pct > 9.8:
            pct_str = f"{Back.RED}{Fore.WHITE}{pct_str}{Style.RESET_ALL}"
        elif pct > 0:
            pct_str = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
        else:
            pct_str = f"{Fore.GREEN}{pct_str}{Style.RESET_ALL}"

        # 简单状态判断
        status = "观察"
        if pct > 9.8:
            status = f"{Fore.RED}🔒涨停{Style.RESET_ALL}"
        elif pct < -9.0:
            status = f"{Fore.GREEN}核按钮{Style.RESET_ALL}"
        elif item['max_pct'] > 9 and pct < 6:
            status = f"{Fore.YELLOW}💥炸板{Style.RESET_ALL}"

        print(
            f"{name:<8} {tag_display} {pct_str:<22} {item['curr_p']:<8} {item['open_pct']:<8.1f} {item['vol_ratio']:<8.0f} {item['max_pct']:<8.1f} {status}")

    print("=" * 140)


# ================= 🚀 启动入口 =================
if __name__ == "__main__":
    print(f"{Fore.CYAN}正在初始化数据...{Fore.RESET}")

    # 1. 加载一次概念库 (启动时读一次即可)
    concept_db = load_concept_db()
    print(f"✅ 已加载概念库: {len(concept_db)} 条数据")

    # 2. 初次加载策略池
    pool = load_strategy_pool(concept_db)

    try:
        while True:
            monitor_loop(pool)
            time.sleep(3)

            # 每分钟热更新一次策略池 (方便盘中加自选)
            if int(time.time()) % 60 < 3:
                # 重新读CSV和剪贴板，但概念库不需要重读(因为盘中不会变)
                new_pool = load_strategy_pool(concept_db)
                # 简单覆盖，保留旧数据的vol信息是个优化点，这里为求稳直接覆盖
                if len(new_pool) >= len(pool):
                    pool = new_pool

    except KeyboardInterrupt:
        print("\n监控结束，祝F佬大赚！")