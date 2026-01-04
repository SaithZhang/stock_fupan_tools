# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (monitor_bid.py) - 收官战最终版
# ==============================================================================
import requests
import pandas as pd
import time
import os
from colorama import init, Fore, Style, Back
import re

init(autoreset=True)

CSV_PATH = 'strategy_pool.csv'
HOT_TOPICS = ["机器人", "航天", "AI", "消费电子"]


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
    broken_limit_count = 0

    for code, data in pool_data.items():
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
                high_p = float(data_list[4])

                if curr_p == 0: curr_p = open_p if open_p > 0 else pre_c

                pct = (curr_p - pre_c) / pre_c * 100 if pre_c > 0 else 0
                open_pct = (open_p - pre_c) / pre_c * 100 if pre_c > 0 and open_p > 0 else 0
                max_pct = (high_p - pre_c) / pre_c * 100 if pre_c > 0 else 0

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

    title_text = f"🔥 F佬/Bo佬 盘中作战室 | {curr_time} | "
    if sentiment == "CRASH":
        title_text += f"{Fore.RED}🛑 退潮 (核按钮:{crash_n}){Style.RESET_ALL}"
    else:
        title_text += f"{Fore.GREEN}✅ 情绪稳 (核按钮:{crash_n}){Style.RESET_ALL}"

    if broken_n > 3:
        title_text += f" | {Back.RED}{Fore.WHITE}⚠️ 炸板潮 ({broken_n}家){Style.RESET_ALL}"
    else:
        title_text += f" | 炸板: {broken_n}家"

    print("=" * 130)
    print(title_text)
    print("=" * 130)
    print(
        f"{'名称':<8} {'标签(紫底=双概念)':<18} {'涨幅':<12} {'现价':<8} {'今开%':<8} {'大哥联动':<12} {'最高%':<8} {'量比':<8} {'AI决策建议'}")
    print("-" * 130)

    for item in pool:
        code = item['sina_code']
        if code not in real_time_data: continue

        name = item.get('name', '-')[:4]
        tag = item.get('tag', '-')
        pct = item['pct']
        open_pct = item['open_pct']
        max_pct = item['max_pct']
        curr_p = item['curr_p']

        # 计算量比 (需要CSV里有vol且非0)
        yesterday_vol = float(item.get('vol', 0))
        current_vol = real_time_data[code]['vol']
        vol_ratio = (current_vol / yesterday_vol * 100) if yesterday_vol > 0 else 0

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

        # 量比颜色
        ratio_str = f"{vol_ratio:.0f}%"
        if vol_ratio > 100:
            ratio_str = f"{Fore.MAGENTA}{ratio_str}{Style.RESET_ALL}"
        elif vol_ratio > 60:
            ratio_str = f"{Fore.YELLOW}{ratio_str}{Style.RESET_ALL}"

        # --- 3. 决策逻辑 ---
        decision = ""
        link_info = "-"

        # A. 炸板检测
        is_broken_limit = (max_pct > 9.5 and pct < 9.0)

        # B. 大哥联动
        dragon_code = item.get('link_dragon')
        dragon_is_strong = False
        if dragon_code and dragon_code in real_time_data:
            d_pct = real_time_data[dragon_code]['pct']
            d_max = real_time_data[dragon_code]['max_pct']

            if d_max > 9.5 and d_pct < 9.0:
                link_info = f"{Back.YELLOW}{Fore.BLACK}大哥炸板{Style.RESET_ALL}"
            elif d_pct > 9.5:
                link_info = f"{Fore.RED}大哥涨停{Style.RESET_ALL}"
                dragon_is_strong = True
            elif d_pct < -5:
                link_info = f"{Fore.GREEN}大哥大跌{Style.RESET_ALL}"

        # ... (在 C. 决策生成 之前插入) ...

        # --- [新增] 弱转强判定逻辑 ---
        is_weak_to_strong = False
        wts_msg = ""

        # 1. 识别昨天的弱势股
        is_rotten = '烂' in tag or '炸' in tag  # 昨天烂板或炸板
        is_drop = '跌' in tag  # 昨天跌停

        # 2. 判定今日竞价是否超预期
        if is_rotten:
            # 烂板/炸板，今天高开 > 1% 就算弱转强
            if open_pct > 1.0:
                is_weak_to_strong = True
                wts_msg = "🔥弱转强(高开)"
        elif is_drop:
            # 跌停股，今天只要红开 > 0% 就算弱转强 (如世宝)
            if open_pct > 0:
                is_weak_to_strong = True
                wts_msg = "🔥弱转强(反核)"

        # 3. 针对F佬说的御银股份 (连板龙头的分歧转一致)
        # 如果是强势连板，但今天开盘分歧(比如低开或平开)，现在拉红了
        if '板' in tag and '烂' not in tag and '炸' not in tag:
            # 昨天硬板，今天开盘弱(<=2%)，但现在拉起来了(>5%)
            if open_pct < 2.0 and pct > 5.0:
                is_weak_to_strong = True
                wts_msg = "🚀分歧转一致"

        # C. 决策生成
        if pct > 9.8:
            decision = f"{Fore.RED}{Style.BRIGHT}封板锁仓{Style.RESET_ALL}"
        elif pct < -9.8:
            decision = f"{Fore.GREEN}跌停不动{Style.RESET_ALL}"
            # [插入] 弱转强 优先级很高，放在涨跌停判断之后
        elif is_weak_to_strong:
            decision = f"{Fore.RED}{Style.BRIGHT}{wts_msg}{Style.RESET_ALL}"
        elif is_broken_limit:
            decision = f"{Fore.MAGENTA}💥炸板!减仓防守{Style.RESET_ALL}"
        elif "大哥炸板" in link_info:
            decision = f"{Fore.RED}⚠️大哥炸了-快跑{Style.RESET_ALL}"
        elif dragon_is_strong:
            decision = f"{Fore.MAGENTA}✅跟随大哥(持有){Style.RESET_ALL}"
        else:
            if '持仓' in tag:
                # 节前止盈策略
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
            f"{name:<8} {tag_display:<26} {pct_str:<20} {curr_p:<8} {open_str:<8} {link_info:<16} {max_pct:<8.1f} {ratio_str:<10} {decision}")

    print("=" * 130)


def load_ths_clipboard_to_df():
    """
    [新增/修复版] 读取同花顺剪贴板文件 (增加GBK兼容和调试信息)
    """
    file_path = 'ths_clipboard.txt'
    if not os.path.exists(file_path):
        return pd.DataFrame()

    print(f"{Fore.MAGENTA}📋 正在解析同花顺文件: {file_path}{Fore.RESET}")

    lines = []
    # 1. 尝试 UTF-8 读取
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 2. 如果失败，尝试 GBK (Windows默认)
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
            print(f"{Fore.YELLOW}ℹ️ 检测到 GBK 编码，已自动兼容{Fore.RESET}")
        except:
            print(f"{Fore.RED}❌ 文件编码识别失败，请另存为 UTF-8{Fore.RESET}")
            return pd.DataFrame()

    new_rows = []
    for line in lines:
        line = line.strip()
        # 跳过空行和表头
        if not line or "代码" in line or "名称" in line:
            continue

            # 使用正则拆分（处理Tab或空格）
        parts = re.split(r'\s+', line)
        if len(parts) < 2: continue

        raw_code = parts[0]  # 如 SZ300045
        name = parts[1]  # 如 华力创通

        # 清洗代码
        sina_code = raw_code.lower()
        pure_code = re.sub(r'\D', '', raw_code)

        # 过滤无效行 (防止读取到末尾的统计行)
        if len(pure_code) != 6: continue

        # 打印一下读到了什么，方便你确认
        # print(f"  -> 识别: {name} ({pure_code})")

        new_rows.append({
            'sina_code': sina_code,
            'name': name,
            'tag': f"午盘/观察/{name}",  # 紫色标签
            'today_pct': 0,
            'open_pct': 0,
            'price': 0,
            'pct_10': 0,
            'link_dragon': '',
            'vol': 0,
            'code': pure_code
        })

    if new_rows:
        print(f"{Fore.BLUE}✅ 成功解析同花顺标的: {len(new_rows)} 只{Fore.RESET}")
        return pd.DataFrame(new_rows)
    else:
        print(f"{Fore.RED}⚠️ 文件读取成功但未解析到有效数据，请检查 txt 内容格式{Fore.RESET}")
        return pd.DataFrame()


def load_strategy_pool():
    """
    [核心加载逻辑] CSV策略池 + TXT临时池 混合加载
    """
    print("正在加载策略池...")

    # 1. 读取主策略 CSV
    if os.path.exists('strategy_pool.csv'):
        df_main = pd.read_csv('strategy_pool.csv', dtype={'code': str})
    else:
        df_main = pd.DataFrame()

    # 2. 读取同花顺 TXT
    df_ths = load_ths_clipboard_to_df()

    # 3. 合并 (如果两个都有数据)
    if not df_ths.empty:
        if not df_main.empty:
            # 关键：去重！如果 CSV 里已经有了，就不要加 TXT 的了
            # 使用 'code' 列作为去重基准
            existing_codes = set(df_main['code'].astype(str).tolist())

            # 只保留 CSV 里没有的
            df_ths = df_ths[~df_ths['code'].isin(existing_codes)]

            # 合并
            df_final = pd.concat([df_main, df_ths], ignore_index=True)
            print(f"✅ 合并加载: 策略池 {len(df_main)} + 临时池 {len(df_ths)} = {len(df_final)} 只")
        else:
            df_final = df_ths
            print(f"⚠️ 未找到CSV，仅加载临时池 {len(df_final)} 只")
    else:
        df_final = df_main
        print(f"✅ 仅加载策略池 {len(df_final)} 只")

    return df_final


if __name__ == "__main__":
    print(f"{Fore.CYAN}正在加载策略池...{Style.RESET_ALL}")

    # 1. 获取 DataFrame 数据 (包含 CSV 和 同花顺剪贴板)
    df_pool = load_strategy_pool()

    if not df_pool.empty:
        # 2. 数据清洗 (防止空值报错)
        if 'link_dragon' not in df_pool.columns:
            df_pool['link_dragon'] = ""
        df_pool['link_dragon'] = df_pool['link_dragon'].fillna('')

        # 3. 关键步骤：转换为字典列表 (monitor_loop 需要这个格式)
        pool = df_pool.to_dict('records')

        print(f"监控启动: {len(pool)} 只标的 (按 Ctrl+C 退出)...")
        try:
            while True:
                monitor_loop(pool)
                time.sleep(3)
        except KeyboardInterrupt:
            print("\n监控结束")
    else:
        print(f"{Fore.RED}错误: 策略池为空！请检查 strategy_pool.csv 或 ths_clipboard.txt{Style.RESET_ALL}")