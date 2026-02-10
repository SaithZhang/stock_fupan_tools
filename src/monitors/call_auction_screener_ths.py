# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py) - 【竞价运行】
# v12.1 全自动实盘版 - (DDD模型 Tag叠加版)
# Last Modified: 2026-01-19
# ==============================================================================
import pandas as pd
import akshare as ak
import os
import re
import sys
import time
import datetime
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

from src.utils.data_loader import load_holdings, HOLDINGS_PATH

# 静态底库目录
THS_DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')
MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')

# 引入情绪周期
sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
try:
    from emotion_cycle import EmotionalCycleEngine
except ImportError:
    class EmotionalCycleEngine:
        def __init__(self): pass

        def get_current_phase(self): return "Rising"


def clean_code(val):
    return re.sub(r'\D', '', str(val)).zfill(6)


# ================= 1. 加载历史底库 =================
try:
    from src.core.data_loader import load_history_map
except ImportError:
    sys.path.append(os.path.join(PROJECT_ROOT, 'src', 'core'))
    from data_loader import load_history_map
from src.utils.data_loader import parse_call_auction_file, get_latest_call_auction_file

# [新增] 引入 DDD 策略模块
try:
    from src.strategies.ddd_mode import calculate_ddd_realtime
except ImportError:
    # 防止找不到模块报错，提供一个空函数
    print(f"{Fore.YELLOW}⚠️ 未找到 DDD 策略模块，将跳过 D佬模型分析{Style.RESET_ALL}")


    def calculate_ddd_realtime(row, history):
        return 0, "", ""


def load_history_data():
    print(f"{Fore.CYAN}📂 [1/3] 正在加载静态底库 (昨收数据 - 统一模块)...{Style.RESET_ALL}")
    data = load_history_map()
    if not data:
        print(f"{Fore.RED}❌ 底库加载失败，请检查 data/input/ths 下的文件{Style.RESET_ALL}")
    else:
        print(f"✅ 底库加载完成，共 {len(data)} 只标的")
    return data


# ================= 板块辅助 =================
def get_sector_map():
    print(f"{Fore.CYAN}📡 [2.5/3] 正在获取板块热度数据 (用于共振分析)...{Style.RESET_ALL}")
    sector_map = {}
    try:
        df_bk = ak.stock_board_industry_name_em()
        for _, row in df_bk.iterrows():
            sector_map[row['板块名称']] = float(row['涨跌幅'])

        df_con = ak.stock_board_concept_name_em()
        df_con = df_con.sort_values(by='涨跌幅', ascending=False).head(100)
        for _, row in df_con.iterrows():
            sector_map[row['板块名称']] = float(row['涨跌幅'])

        print(f"✅ 板块情绪加载完成，捕捉到 {len(sector_map)} 个热点方向")
        return sector_map
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 板块数据获取略过: {e}{Style.RESET_ALL}")
        return {}


# ================= 2. 获取实时数据 =================
def load_call_auction_data_from_file():
    file_path = get_latest_call_auction_file()
    if not file_path: return None

    filename = os.path.basename(file_path)
    print(f"{Fore.CYAN}📂 [2A/3] 检测到本地竞价文件: {filename}，优先加载...{Style.RESET_ALL}")

    df = parse_call_auction_file(file_path)
    if df is not None and not df.empty:
        print(f"✅ 从本地文件加载了 {len(df)} 条竞价数据")
        return df
    return None


def get_live_data():
    local_df = load_call_auction_data_from_file()
    if local_df is not None and not local_df.empty:
        return local_df

    print(f"{Fore.CYAN}📡 [2B/3] 未找到本地文件，请求 Akshare 实时行情...{Style.RESET_ALL}")
    start_time = time.time()
    try:
        df = ak.stock_zh_a_spot_em()
        rename_map = {
            '代码': 'code', '名称': 'name', '涨跌幅': 'open_pct',
            '成交额': 'auc_amt', '最新价': 'current_price'
        }
        df = df.rename(columns=rename_map)
        df['code'] = df['code'].astype(str)
        df = df[df['open_pct'].notnull()]
        df['auc_amt'] = df['auc_amt'].fillna(0) / 10000.0  # 元转万

        print(f"✅ 实时数据获取成功，耗时 {time.time() - start_time:.2f}秒，共 {len(df)} 条")
        return df
    except Exception as e:
        print(f"{Fore.RED}❌ Akshare 接口失败: {e}{Style.RESET_ALL}")
        return pd.DataFrame()


# ================= 加载策略池 =================
def load_strategy_pool():
    pool_path = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
    if not os.path.exists(pool_path): return {}
    pool_map = {}
    try:
        df = pd.read_csv(pool_path)
        for _, row in df.iterrows():
            code = str(row.get('sina_code', ''))[2:]
            if not code: code = str(row.get('code', '')).zfill(6)
            pool_map[code] = str(row.get('tag', ''))
    except Exception as e:
        print(f"⚠️ 策略池加载失败: {e}")
    return pool_map


def load_manual_focus():
    if not os.path.exists(MANUAL_FOCUS_PATH): return set()
    s = set()
    try:
        with open(MANUAL_FOCUS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        s.add(p.zfill(6))
                    else:
                        s.add(p)
    except:
        pass
    return s


# ================= 3. 策略判定 (核心修改部分) =================
def analyze_stock(row, history_info, pool_map, phase, sector_map=None):
    """
    策略判定核心：
    1. 计算基础指标
    2. 判断 F佬/A佬 战法 (深水/弱转强等)
    3. 判断 DDD 模型 (作为加分项和 Tag 叠加)
    """
    code = row['code']
    name = row['name']

    # 1. 实时数据解析
    try:
        open_pct = float(row.get('open_pct', 0))
        auc_amt = float(row.get('auc_amt', 0))  # 万
        last_amt = float(row.get('last_amt', 0))  # 万

        # 补救 last_amt
        if last_amt == 0:
            raw_yest = row.get('昨日成交额', row.get('昨成交', '0'))
            raw_str = str(raw_yest).strip()
            try:
                if '亿' in raw_str:
                    last_amt = float(raw_str.replace('亿', '')) * 10000
                elif '万' in raw_str:
                    last_amt = float(raw_str.replace('万', ''))
                else:
                    last_amt = float(raw_str) / 10000
            except:
                last_amt = 0
    except Exception as e:
        return None

    # 2. 历史数据匹配
    if code not in history_info: return None
    info = history_info[code]

    circ_mv = info['circ_mv']
    if circ_mv > 100_000_000: circ_mv /= 10000.0  # 统一转为万

    yest_pct = info['yest_pct']
    boards = info['boards']
    industry = info.get('industry', '未知')

    if last_amt == 0 or circ_mv == 0: return None

    # 3. 核心指标
    ratio_yest = (auc_amt / last_amt * 100)
    ratio_mv = (auc_amt / circ_mv * 100)

    # 4. 板块分析
    sector_pct = 0.0
    sector_display = industry
    is_sector_hot = False
    is_sector_weak = False

    if sector_map and industry in sector_map:
        sector_pct = sector_map[industry]
        if sector_pct >= 1.5:
            is_sector_hot = True
            sector_display = f"{Fore.RED}🔥{industry}:{sector_pct:.1f}%{Style.RESET_ALL}"
        elif sector_pct < -0.5:
            is_sector_weak = True
            sector_display = f"{Fore.GREEN}❄️{industry}:{sector_pct:.1f}%{Style.RESET_ALL}"
        else:
            sector_display = f"{industry}:{sector_pct:.1f}%"

    # ================= 策略判断开始 =================

    # 基础变量
    score = 60
    decision = "观察"
    fail_msg = ""
    pool_tag = pool_map.get(code, "")

    # 过滤阈值
    min_auc = 300_0000
    if code in pool_map: min_auc = 0
    if auc_amt < min_auc: return None

    # A. 一字板 (直接返回，不走DDD)
    if open_pct > 9.8:
        score = 0
        if code in pool_map: score = 90
        return {
            'code': code, 'name': name, 'score': score,
            'decision': f"{Fore.BLUE}一字板{Style.RESET_ALL}",
            'open_pct': open_pct, 'auc': auc_amt, 'yest_pct': yest_pct,
            'boards': boards, 'r_mv': ratio_mv, 'circ_mv': circ_mv,
            'sector_info': sector_display, 'last_amt': last_amt, 'r_yest': ratio_yest
        }

    # B. F佬/A佬 主策略逻辑
    # ----------------------------------------
    is_main_strategy_hit = False

    # B1. 深水低吸
    if open_pct <= -5.0:
        if "低吸" in pool_tag or "趋势" in pool_tag or "F佬" in pool_tag:
            decision = f"{Fore.GREEN}✅ 深水低吸{Style.RESET_ALL}"
            score = 88
            is_main_strategy_hit = True
        else:
            fail_msg = f"深水({open_pct}%)"

    # B2. A大焚诀 (核按钮反包)
    elif "A大焚诀" in pool_tag or "F佬" in pool_tag:
        if open_pct > 0:
            decision = f"{Fore.RED}🔥 A大反包{Style.RESET_ALL}"
            score = 90
            is_main_strategy_hit = True

            if is_sector_hot:
                score = 98
                decision += f" {Back.RED}{Fore.WHITE}共振{Style.RESET_ALL}"
            elif is_sector_weak:
                score -= 15
                decision += f" {Fore.YELLOW}⚠️孤狼{Style.RESET_ALL}"
            if ratio_mv > 1.0:
                decision += "/爆量"
                score += 2
        else:
            fail_msg = f"未翻红"
            score = 50
            decision = f"{Fore.YELLOW}等待翻红{Style.RESET_ALL}"
            # 这里虽然 fail，但如果是关注票，可能还是想看，暂不return

    # B3. 常规弱转强
    elif open_pct < 3.0:
        if ratio_mv > 0.8:
            decision = f"{Fore.MAGENTA}★ 弱转强{Style.RESET_ALL}"
            is_main_strategy_hit = True
            if is_sector_hot:
                score += 10
                decision += f"/{industry}强"
        else:
            if not pool_tag: fail_msg = f"竞价弱"

    # B4. 高开处理
    else:
        if open_pct > 5.0 and open_pct < 9.8:
            if "加速" in pool_tag or is_sector_hot:
                decision = "加速预期"
                is_main_strategy_hit = True
            else:
                decision = f"{Fore.YELLOW}⚠️ 高开风险{Style.RESET_ALL}"
                score = 60

    # C. DDD 策略检测 (叠加 Tag)
    # ----------------------------------------
    # 构造 DDD 需要的参数
    ddd_history = {
        'circ_mv': info.get('circ_mv', 0),
        'yest_amt': info.get('yest_amt', 0),
        'boards': info.get('boards', 0),
        'last_bid_amt': info.get('yest_bid_amt', 0)
    }

    ddd_score, ddd_dec, ddd_tag = calculate_ddd_realtime(row, ddd_history)

    if ddd_score > 0:
        # 命中 DDD 模型
        # 如果前面主策略也命中了，分数叠加；如果前面没命中，以 DDD 分数为准
        if is_main_strategy_hit:
            score += 10  # 叠加分
        else:
            score = max(score, ddd_score)  # 择优
            if decision == "观察": decision = ""  # 清空默认值

        # 打上 DDD 标签
        # 使用紫色高亮显示 DDD 标签
        ddd_label = f" {Fore.MAGENTA}[{ddd_tag}]{Style.RESET_ALL}"
        decision += ddd_label

        # 如果之前因为 fail_msg (比如竞价弱) 被标记失败，但符合 DDD，则复活
        fail_msg = ""

        # ----------------------------------------

    # 池子标记
    if code in pool_map:
        if score < 80: score += 10
        decision += f"{Back.MAGENTA}{Fore.WHITE} 池 {Style.RESET_ALL}"
        # 如果有 fail_msg 但在池子里，给个观察机会
        if fail_msg:
            decision = f"{Fore.YELLOW}{fail_msg}{Style.RESET_ALL}"
            score = 70
            fail_msg = ""  # 清空失败，允许输出

    # 如果既没有命中主策略，也没有命中 DDD，且有失败原因 -> 抛弃
    if fail_msg: return None

    # 兜底：如果分数太低且没有任何策略标签 -> 抛弃
    if score < 60 and "DDD" not in decision and "池" not in decision: return None

    return {
        'code': code,
        'name': name,
        'score': score,
        'decision': decision,
        'open_pct': open_pct,
        'auc': auc_amt,
        'r_yest': ratio_yest,
        'r_mv': ratio_mv,
        'yest_pct': yest_pct,
        'boards': boards,
        'circ_mv': circ_mv,
        'tag': pool_tag,
        'sector_info': sector_display,
        'last_amt': last_amt
    }


# ================= 🚀 主程序 =================
def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (Akshare Plus版) {Style.RESET_ALL}")
    print("=" * 120)

    # 0. 情绪周期
    current_phase = "Rising"
    print(f"{Fore.CYAN}🌊 [0/4] 正在分析情绪周期... {Fore.MAGENTA}{current_phase}{Style.RESET_ALL}")

    # 1. 加载数据
    history_map = load_history_data()
    if not history_map: return
    pool_map = load_strategy_pool()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    valid_codes = set(pool_map.keys()) | set(holdings.keys())
    for item in manual_focus:
        if item.isdigit(): valid_codes.add(item)

    # 2. 获取实时数据
    live_df = get_live_data()
    if live_df.empty: return

    # 2.5 获取板块
    sector_map = get_sector_map()

    print(f"{Fore.CYAN}⚙️ [3/3] 正在进行策略计算 (F佬/A佬 + DDD模型 Tag版)...{Style.RESET_ALL}")

    results = []
    seen_codes = set()

    for _, row in live_df.iterrows():
        code = clean_code(row['code'])
        if code in seen_codes: continue
        seen_codes.add(code)

        # 过滤范围 (持仓+池子+手动)
        is_target = False
        if code in valid_codes: is_target = True
        if not is_target and str(row['name']) in manual_focus: is_target = True
        if not is_target: continue

        res = analyze_stock(row, history_map, pool_map, current_phase, sector_map)
        if res:
            results.append(res)

    # 3. 排序与展示
    results.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print("\n" + "=" * 135)
    print(
        f"📊 实时监控报告 | 时间: {datetime.datetime.now().strftime('%H:%M:%S')} | 扫描: {len(live_df)} | 命中: {len(results)}")
    print(
        f"{'代码':<8} {'名称':<8} {'竞价%':<6} {'昨幅%':<6} {'连板':<6} {'市值':<8} {'昨额':<8} {'板块情况':<12} {'AI决策 (含DDD Tag)'}")
    print("-" * 140)

    count = 0
    for item in results:
        if item['score'] < 40: continue

        count += 1
        auc_str = f"{int(item['auc'])}万"

        yest_amt_val = item.get('last_amt', 0)
        if yest_amt_val == 0 and item.get('r_yest', 0) > 0:
            yest_amt_val = item['auc'] / (item['r_yest'] / 100)

        if yest_amt_val > 10000:
            yest_str = f"{yest_amt_val / 10000:.1f}亿"
        else:
            yest_str = f"{int(yest_amt_val)}万"

        yest_pct = item.get('yest_pct', 0)
        c_yest = Fore.RED if yest_pct > 0 else Fore.GREEN
        c_open = Fore.RED if item['open_pct'] > 0 else Fore.GREEN

        boards = item.get('boards', 0)
        boards_str = f"{Fore.RED}{boards}板{Style.RESET_ALL}" if boards >= 2 else ""

        mv_val = item.get('circ_mv', 0)
        mv_str = f"{mv_val / 10000.0:.1f}亿"

        print(
            f"{item['code']:<8} "
            f"{item['name'][:4]:<8} "
            f"{c_open}{item['open_pct']:>6.2f}{Style.RESET_ALL} "
            f"{c_yest}{yest_pct:>6.1f}{Style.RESET_ALL} "
            f"{boards_str:<6} "
            f"{mv_str:<8} "
            f"{yest_str:<8} "
            f"{item.get('sector_info', ''):<20} "
            f"{item['decision']} "
            f"额:{auc_str}"
        )

    if count == 0:
        print(f"{Fore.YELLOW}暂无符合【严格标准】的标的，请稍候再试...{Style.RESET_ALL}")
    print("=" * 135)


if __name__ == "__main__":
    now = datetime.datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute < 25):
        print(f"{Fore.YELLOW}⚠️ 提示：当前时间早于 9:25，Akshare 获取的成交额可能不是最终竞价金额。{Style.RESET_ALL}")
    main()