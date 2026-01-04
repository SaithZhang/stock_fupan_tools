# ==============================================================================
# 📌 3. F佬/Bo佬 智能盘中监控系统 (src/monitors/realtime_watch.py) - V4.1 路径增强版
# ==============================================================================
import requests
import pandas as pd
import time
import os
from colorama import init, Fore, Style, Back
import re
import sys

# 适配 Windows 控制台编码
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 (自动定位) =================
# 获取当前脚本所在目录 (src/monitors)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 向推两级找到项目根目录 (stock_fupan_tools)
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# 定义绝对路径
CSV_PATH = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
THS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths_clipboard.txt')

print(f"{Fore.CYAN}🔧 监控数据源定位: {CSV_PATH}{Fore.RESET}")

# 重点关注概念 (用于高亮显示)
HOT_TOPICS = ["机器人", "航天", "AI", "消费电子", "算力", "低空", "固态"]


# ================= 🛠️ 数据加载函数 =================

def load_ths_clipboard_to_df():
    """读取同花顺剪贴板 (含编码自动纠错)"""
    if not os.path.exists(THS_PATH):
        return pd.DataFrame()

    lines = []
    try:
        # 优先尝试 UTF-8
        with open(THS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 失败则尝试 GBK
        try:
            with open(THS_PATH, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except:
            return pd.DataFrame()

    new_rows = []
    for line in lines:
        line = line.strip()
        if not line or "代码" in line or "名称" in line:
            continue

        parts = re.split(r'\s+', line)
        if len(parts) < 2: continue

        raw_code = parts[0]
        name = parts[1]

        sina_code = raw_code.lower()
        pure_code = re.sub(r'\D', '', raw_code)

        if len(pure_code) != 6: continue

        new_rows.append({
            'sina_code': sina_code,
            'name': name,
            'tag': f"同花顺/{name}",
            'today_pct': 0,
            'open_pct': 0,
            'price': 0,
            'pct_10': 0,
            'link_dragon': '',
            'vol': 0,
            'code': pure_code
        })

    return pd.DataFrame(new_rows)


def load_strategy_pool():
    """加载策略池 (CSV + 剪贴板混合)"""
    # 1. 读取 CSV (由 pool_generator 生成)
    if os.path.exists(CSV_PATH):
        try:
            df_main = pd.read_csv(CSV_PATH, dtype={'code': str, 'sina_code': str})
        except Exception as e:
            print(f"{Fore.RED}读取CSV失败: {e}{Fore.RESET}")
            df_main = pd.DataFrame()
    else:
        print(f"{Fore.YELLOW}⚠️ 未找到策略池 CSV，请先运行 pool_generator.py{Fore.RESET}")
        df_main = pd.DataFrame()

    # 2. 读取同花顺剪贴板 (作为盘中临时补充)
    df_ths = load_ths_clipboard_to_df()

    # 3. 合并与去重
    if not df_ths.empty:
        if not df_main.empty:
            # 避免重复添加：如果 CSV 里已经有了，就不加 TXT 的
            existing_codes = set(df_main['code'].astype(str).tolist())
            df_ths = df_ths[~df_ths['code'].isin(existing_codes)]

            df_final = pd.concat([df_main, df_ths], ignore_index=True)
        else:
            df_final = df_ths
    else:
        df_final = df_main

    # 数据清洗
    if not df_final.empty:
        if 'link_dragon' not in df_final.columns:
            df_final['link_dragon'] = ""
        df_final['link_dragon'] = df_final['link_dragon'].fillna('')
        # 确保 code 列存在
        if 'sina_code' not in df_final.columns and 'code' in df_final.columns:
            df_final['sina_code'] = df_final['code'].apply(
                lambda x: f"sz{x}" if str(x).startswith(('0', '3')) else f"sh{x}")

        return df_final.to_dict('records')

    return []


# ================= 📊 核心监控逻辑 =================

def fetch_sina_data(sina_codes):
    """批量获取新浪实时行情"""
    if not sina_codes: return {}

    # 新浪接口限制一次最多请求约80-100个，切片处理
    chunk_size = 80
    parsed_data = {}

    for i in range(0, len(sina_codes), chunk_size):
        chunk = sina_codes[i:i + chunk_size]
        code_str = ",".join(chunk)
        url = f"http://hq.sinajs.cn/list={code_str}"
        headers = {'Referer': 'https://finance.sina.com.cn'}

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

                    # 竞价/停牌处理
                    if curr_p == 0: curr_p = open_p if open_p > 0 else pre_c
                    if pre_c == 0: continue

                    pct = (curr_p - pre_c) / pre_c * 100
                    open_pct = (open_p - pre_c) / pre_c * 100 if open_p > 0 else 0
                    max_pct = (high_p - pre_c) / pre_c * 100

                    parsed_data[code] = {
                        'curr_p': curr_p,
                        'pre_c': pre_c,
                        'pct': pct,
                        'open_pct': open_pct,
                        'max_pct': max_pct,
                        'vol': int(data_list[8]) // 100,
                        'amt': float(data_list[9])
                    }
                except:
                    continue
        except:
            pass

    return parsed_data


def get_market_sentiment(pool_data):
    """计算简单的情绪指标"""
    high_tier_count = 0
    crash_count = 0
    broken_limit_count = 0

    for code, data in pool_data.items():
        if data.get('max_pct', 0) > 9.5 and data.get('pct', 0) < 9.0:
            broken_limit_count += 1

        tag = str(data.get('tag', ''))
        if '板' in tag:
            high_tier_count += 1
            if data.get('pct', 0) < -5: crash_count += 1

    status = "NORMAL"
    if high_tier_count > 0 and (crash_count / high_tier_count > 0.3 or crash_count >= 3):
        status = "CRASH"

    return status, crash_count, broken_limit_count


def monitor_loop(pool):
    # 1. 提取所有需要查询的代码 (包括关联的大哥)
    all_codes = set()
    for item in pool:
        if 'sina_code' in item:
            all_codes.add(item['sina_code'])
        if item['link_dragon']:
            all_codes.add(item['link_dragon'])

    # 2. 获取实时行情
    real_time_data = fetch_sina_data(list(all_codes))
    if not real_time_data: return

    # 3. 合并数据到 pool item
    active_pool = []
    for item in pool:
        code = item.get('sina_code')
        if code in real_time_data:
            # 浅拷贝避免修改原始字典造成污染
            new_item = item.copy()
            new_item.update(real_time_data[code])
            active_pool.append(new_item)

    # 4. 计算情绪
    # sentiment, crash_n, broken_n = get_market_sentiment({x['sina_code']: x for x in active_pool})
    # (简化版显示)

    # 5. 清屏与打印表头
    os.system('cls' if os.name == 'nt' else 'clear')
    curr_time = time.strftime('%H:%M:%S')

    print("=" * 145)
    print(f"🔥 F佬/Bo佬 盘中作战室 | {curr_time} | 监控标的: {len(active_pool)}只")
    print("=" * 145)
    print(
        f"{'名称':<8} {'核心标签':<25} {'涨幅':<12} {'现价':<8} {'今开%':<8} {'联动状态':<15} {'最高%':<8} {'量比':<8} {'AI决策建议'}")
    print("-" * 145)

    # 6. 逐行打印
    for item in active_pool:
        name = item.get('name', '-')[:4]
        tag = str(item.get('tag', '-'))
        pct = item['pct']
        open_pct = item['open_pct']
        max_pct = item['max_pct']
        curr_p = item['curr_p']
        code = item['sina_code']

        # 计算量比
        yesterday_vol = float(item.get('vol', 0))
        current_vol = item['vol']
        vol_ratio = (current_vol / yesterday_vol * 100) if yesterday_vol > 0 else 0

        # --- 渲染逻辑 ---

        # A. 标签高亮
        hit_count = sum(1 for topic in HOT_TOPICS if topic in tag)
        # 截断过长的标签
        tag_display = tag[:22] + ".." if len(tag) > 24 else tag

        if hit_count >= 2:
            tag_display = f"{Back.MAGENTA}{Fore.WHITE}{tag_display:<25}{Style.RESET_ALL}"
        elif hit_count == 1:
            tag_display = f"{Fore.CYAN}{tag_display:<25}{Style.RESET_ALL}"
        else:
            tag_display = f"{tag_display:<25}"

        # B. 涨跌幅颜色
        pct_str = f"{pct:+.2f}%"
        if pct > 9.8:
            pct_str = f"{Fore.RED}{Style.BRIGHT}🚀{pct_str}{Style.RESET_ALL}"
        elif pct > 0:
            pct_str = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
        elif pct < -9.0:
            pct_str = f"{Fore.GREEN}🤮{pct_str}{Style.RESET_ALL}"
        elif pct < 0:
            pct_str = f"{Fore.GREEN}{pct_str}{Style.RESET_ALL}"

        # C. 决策逻辑
        decision = ""
        link_info = "-"

        # 联动检测
        dragon_code = item.get('link_dragon')
        dragon_strong = False

        if dragon_code and dragon_code in real_time_data:
            d_data = real_time_data[dragon_code]
            if d_data['max_pct'] > 9.5 and d_data['pct'] < 9.0:
                link_info = f"{Back.YELLOW}{Fore.BLACK}大哥炸板{Style.RESET_ALL}"
            elif d_data['pct'] > 9.5:
                link_info = f"{Fore.RED}大哥涨停{Style.RESET_ALL}"
                dragon_strong = True
            elif d_data['pct'] < -5:
                link_info = f"{Fore.GREEN}大哥大跌{Style.RESET_ALL}"

        # 弱转强检测
        is_wts = False
        wts_msg = ""
        # 烂板/炸板/跌停 次日高开/红开
        if ('烂' in tag or '炸' in tag) and open_pct > 1.0:
            is_wts = True;
            wts_msg = "🔥弱转强"
        elif '跌' in tag and open_pct > 0:
            is_wts = True;
            wts_msg = "🔥反核"

        # 生成建议
        if pct > 9.8:
            decision = f"{Fore.RED}🔒锁仓{Style.RESET_ALL}"
        elif "大哥炸板" in link_info:
            decision = f"{Fore.RED}⚠️快跑{Style.RESET_ALL}"
        elif is_wts:
            decision = f"{Fore.MAGENTA}{wts_msg}{Style.RESET_ALL}"
        elif max_pct > 9.5 and pct < 9.0:
            decision = f"{Fore.YELLOW}💥炸板{Style.RESET_ALL}"
        elif vol_ratio > 150:
            decision = f"{Fore.CYAN}放量{Style.RESET_ALL}"
        else:
            decision = "观察"

        # 格式化输出
        ratio_str = f"{vol_ratio:.0f}%"
        if vol_ratio > 100: ratio_str = f"{Fore.MAGENTA}{ratio_str}{Style.RESET_ALL}"

        open_str = f"{open_pct:+.1f}%"
        if open_pct > 0:
            open_str = f"{Fore.RED}{open_str}{Style.RESET_ALL}"
        else:
            open_str = f"{Fore.GREEN}{open_str}{Style.RESET_ALL}"

        print(
            f"{name:<8} {tag_display} {pct_str:<22} {curr_p:<8} {open_str:<18} {link_info:<24} {max_pct:<8.1f} {ratio_str:<18} {decision}")

    print("=" * 145)


# ================= 🚀 启动入口 =================

if __name__ == "__main__":
    print(f"{Fore.CYAN}正在加载策略池...{Style.RESET_ALL}")

    # 首次加载
    pool = load_strategy_pool()

    if not pool:
        print(f"{Fore.RED}策略池为空，请检查 data/output/strategy_pool.csv{Style.RESET_ALL}")
    else:
        print(f"监控启动: {len(pool)} 只标的 (按 Ctrl+C 退出)...")
        try:
            while True:
                monitor_loop(pool)
                # 3秒刷新一次
                time.sleep(3)

                # 可选：每隔1分钟重新加载一次CSV (方便盘中手动改CSV后生效)
                # if int(time.time()) % 60 < 4:
                #     pool = load_strategy_pool()

        except KeyboardInterrupt:
            print("\n监控结束")