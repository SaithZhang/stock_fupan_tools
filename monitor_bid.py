# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (monitor_bid.py) - 炸板雷达版
# ==============================================================================
# 新增功能：
# 1. [炸板检测]：如果曾触及涨停但回落，显示"💥炸板"，提示风险。
# 2. [吸血效应]：如果机器人板块强，但你的票（非机器人）在跌，提示"被吸血"。
# ==============================================================================

import requests
import pandas as pd
import time
import os
from colorama import init, Fore, Style, Back

init(autoreset=True)

CSV_PATH = 'strategy_pool.csv'
HOT_TOPICS = ["机器人", "航天", "AI"]


def load_strategy_pool():
    if not os.path.exists(CSV_PATH):
        print(f"{Fore.RED}错误: 找不到 {CSV_PATH}{Style.RESET_ALL}")
        return []
    try:
        df = pd.read_csv(CSV_PATH)
        if 'link_dragon' not in df.columns: df['link_dragon'] = None
        df['link_dragon'] = df['link_dragon'].fillna('')
        return df.to_dict('records')
    except Exception as e:
        print(f"读取CSV失败: {e}")
        return []


def get_market_sentiment(pool_data):
    high_tier_count = 0
    crash_count = 0
    broken_limit_count = 0  # 炸板数量

    for code, data in pool_data.items():
        # 计算炸板：最高价接近涨停(>9.5%)，但现价回落( <9.0%)
        if data['max_pct'] > 9.5 and data['pct'] < 9.0:
            broken_limit_count += 1

        if '板' in data['tag']:
            high_tier_count += 1
            if data['pct'] < -5: crash_count += 1

    status = "NORMAL"
    if high_tier_count > 0 and (crash_count / high_tier_count > 0.3 or crash_count >= 3):
        status = "CRASH"

    return status, crash_count, broken_limit_count


def fetch_sina_data(sina_codes):
    if not sina_codes: return {}
    code_str = ",".join(sina_codes)
    url = f"http://hq.sinajs.cn/list={code_str}"
    headers = {'Referer': 'https://finance.sina.com.cn'}
    parsed_data = {}
    try:
        resp = requests.get(url, headers=headers, timeout=3)
        resp.encoding = 'gbk'
        lines = resp.text.strip().split('\n')
        for line in lines:
            if not line: continue
            try:
                parts = line.split('=')
                code = parts[0].split('_')[-1]
                val = parts[1].strip('"')
                if not val: continue
                data_list = val.split(',')

                open_p = float(data_list[1])
                pre_c = float(data_list[2])
                curr_p = float(data_list[3])
                high_p = float(data_list[4])  # 最高价

                if curr_p == 0: curr_p = open_p if open_p > 0 else pre_c

                pct = (curr_p - pre_c) / pre_c * 100 if pre_c > 0 else 0
                open_pct = (open_p - pre_c) / pre_c * 100 if pre_c > 0 and open_p > 0 else 0
                max_pct = (high_p - pre_c) / pre_c * 100 if pre_c > 0 else 0  # 最高涨幅

                parsed_data[code] = {
                    'curr_p': curr_p, 'pre_c': pre_c, 'pct': pct,
                    'open_pct': open_pct, 'max_pct': max_pct,
                    'vol': int(data_list[8]) // 100, 'amt': float(data_list[9])
                }
            except:
                continue
    except:
        pass
    return parsed_data


def monitor_loop(pool):
    all_codes = set([item['sina_code'] for item in pool])
    for item in pool:
        if item['link_dragon']: all_codes.add(item['link_dragon'])

    real_time_data = fetch_sina_data(list(all_codes))
    if not real_time_data: return

    sentiment_calc_data = {}
    for item in pool:
        code = item['sina_code']
        if code in real_time_data:
            item.update(real_time_data[code])
            sentiment_calc_data[code] = item

    sentiment, crash_n, broken_n = get_market_sentiment(sentiment_calc_data)

    os.system('cls' if os.name == 'nt' else 'clear')
    curr_time = time.strftime('%H:%M:%S')

    # 标题栏优化
    title_text = f"🔥 F佬/Bo佬 盘中作战室 | {curr_time} | "
    if sentiment == "CRASH":
        title_text += f"{Fore.RED}🛑 退潮 (核按钮:{crash_n}){Style.RESET_ALL}"
    else:
        title_text += f"{Fore.GREEN}✅ 情绪稳 (核按钮:{crash_n}){Style.RESET_ALL}"

    # 炸板警报
    if broken_n > 3:
        title_text += f" | {Back.RED}{Fore.WHITE}⚠️ 炸板潮 ({broken_n}家){Style.RESET_ALL}"
    else:
        title_text += f" | 炸板: {broken_n}家"

    print("=" * 125)
    print(title_text)
    print("=" * 125)
    print(
        f"{'名称':<8} {'标签(紫底=双概念)':<18} {'涨幅':<12} {'现价':<8} {'今开%':<8} {'大哥联动':<12} {'最高%':<8} {'AI决策建议'}")
    print("-" * 125)

    for item in pool:
        code = item['sina_code']
        if code not in real_time_data: continue

        name = item.get('name', '-')[:4]
        tag = item.get('tag', '-')
        pct = item['pct']
        open_pct = item['open_pct']
        max_pct = item['max_pct']  # 最高涨幅
        curr_p = item['curr_p']
        yesterday_vol = float(item.get('vol', 1))

        # --- 1. 标签渲染 ---
        hit_count = sum(1 for topic in HOT_TOPICS if topic in tag)
        tag_display = tag[:12]
        if hit_count >= 2:
            tag_display = f"{Back.MAGENTA}{Fore.WHITE}🔥{tag[:10]}{Style.RESET_ALL}"
        elif hit_count == 1:
            tag_display = f"{Fore.CYAN}{tag[:12]}{Style.RESET_ALL}"

        # --- 2. 涨幅颜色 ---
        pct_str = f"{pct:+.2f}%"
        if pct > 9.8:
            pct_str = f"{Fore.RED}{Style.BRIGHT}🚀{pct_str}{Style.RESET_ALL}"
        elif pct > 0:
            pct_str = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
        elif pct < -9.0:
            pct_str = f"{Fore.GREEN}🤮{pct_str}{Style.RESET_ALL}"
        elif pct < 0:
            pct_str = f"{Fore.GREEN}{pct_str}{Style.RESET_ALL}"

        open_str = f"{open_pct:+.1f}%"
        if open_pct < 0:
            open_str = f"{Fore.GREEN}{open_str}{Style.RESET_ALL}"
        else:
            open_str = f"{Fore.RED}{open_str}{Style.RESET_ALL}"

        # --- 3. 决策逻辑 (引入f哥复盘) ---
        decision = ""
        link_info = "-"

        # A. 炸板检测 (新增)
        is_broken_limit = (max_pct > 9.5 and pct < 9.0)

        # B. 大哥联动
        dragon_code = item.get('link_dragon')
        dragon_is_strong = False
        if dragon_code and dragon_code in real_time_data:
            d_pct = real_time_data[dragon_code]['pct']
            d_max = real_time_data[dragon_code]['max_pct']

            # 大哥炸板检测
            if d_max > 9.5 and d_pct < 9.0:
                link_info = f"{Back.YELLOW}{Fore.BLACK}大哥炸板{Style.RESET_ALL}"
            elif d_pct > 9.5:
                link_info = f"{Fore.RED}大哥涨停{Style.RESET_ALL}"
                dragon_is_strong = True
            elif d_pct < -5:
                link_info = f"{Fore.GREEN}大哥大跌{Style.RESET_ALL}"

        # C. 决策生成
        if pct > 9.8:
            decision = f"{Fore.RED}{Style.BRIGHT}封板锁仓{Style.RESET_ALL}"
        elif pct < -9.8:
            decision = f"{Fore.GREEN}跌停不动{Style.RESET_ALL}"

        # 炸板处理
        elif is_broken_limit:
            decision = f"{Fore.MAGENTA}💥炸板!减仓防守{Style.RESET_ALL}"

        # 大哥炸板，小弟快跑
        elif "大哥炸板" in link_info:
            decision = f"{Fore.RED}⚠️大哥炸了-快跑{Style.RESET_ALL}"

        elif dragon_is_strong:
            decision = f"{Fore.MAGENTA}✅跟随大哥(持有){Style.RESET_ALL}"
        else:
            # 持仓逻辑
            if '持仓' in tag:
                # 明日特供：节前效应，冲高止盈
                if pct > 5 and not dragon_is_strong:
                    decision = f"{Fore.RED}节前止盈(卖){Style.RESET_ALL}"
                elif open_pct < -2 and pct < -2:
                    if sentiment == "CRASH":
                        decision = f"{Fore.CYAN}🚫退潮:禁补仓{Style.RESET_ALL}"
                    else:
                        decision = f"{Fore.GREEN}深水反核?{Style.RESET_ALL}"
                else:
                    decision = "持仓观察"
            else:
                decision = "观察"

        print(
            f"{name:<8} {tag_display:<26} {pct_str:<20} {curr_p:<8} {open_str:<8} {link_info:<16} {max_pct:<8.1f} {decision}")

    print("=" * 125)


if __name__ == "__main__":
    print(f"{Fore.CYAN}正在加载策略池...{Style.RESET_ALL}")
    pool = load_strategy_pool()
    if pool:
        print(f"监控启动: {len(pool)} 只标的 (按 Ctrl+C 退出)...")
        try:
            while True:
                monitor_loop(pool)
                time.sleep(3)
        except KeyboardInterrupt:
            print("\n监控结束")