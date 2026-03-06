# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py)
# v7.2 老龙破局版 - (增加“巨量滞涨”防雷 + “小弟反推老龙”点火识别)
# ==============================================================================
import pandas as pd
import os
import re
import sys
import io
import time
from colorama import init, Fore, Style, Back

# 解决 Windows 终端输出编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import load_holdings, HOLDINGS_PATH

MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')


def clean_code(val):
    return re.sub(r'\D', '', str(val)).zfill(6)


def parse_chinese_money(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).strip()
    if not val_str or val_str == '--' or val_str.lower() == 'nan': return 0.0
    try:
        if '亿' in val_str:
            return float(val_str.replace('亿', '').replace('万', '').replace('+', '').strip()) * 10000.0
        elif '万' in val_str:
            return float(val_str.replace('万', '').replace('+', '').strip())
        else:
            return float(val_str.replace('+', ''))
    except:
        return 0.0


def parse_pct(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace('%', '').replace('+', '')
    if not val_str or val_str == '--' or val_str.lower() == 'nan': return 0.0
    try:
        return float(val_str)
    except:
        return 0.0


# ================= 1. 加载盘后底库与策略池 =================
def load_tushare_pool_and_history():
    print(f"{Fore.CYAN}📂 [1/4] 正在加载 Tushare 盘后底库 (strategy_pool.csv)...{Style.RESET_ALL}")
    pool_path = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
    history_map, pool_map = {}, {}

    if not os.path.exists(pool_path):
        print(f"{Fore.RED}❌ 未找到 Tushare 底库: {pool_path}{Style.RESET_ALL}")
        return history_map, pool_map

    try:
        df = pd.read_csv(pool_path, dtype=str)
        df.columns = df.columns.str.strip()

        for _, row in df.iterrows():
            code = clean_code(row.get('code', row.get('ts_code', row.get('代码', ''))))
            if not code: continue

            tag = str(row.get('tag', row.get('策略标签', ''))).strip()
            if tag.lower() == 'nan': tag = ""
            if tag: pool_map[code] = tag

            pct_val = row.get('pct_chg', row.get('涨跌幅', row.get('pct', row.get('today_pct', 0))))
            yest_pct = parse_pct(pct_val)

            limit_val = str(row.get('limit_status', row.get('连板数', row.get('连板高度', '0'))))
            boards = int(re.findall(r'\d+', limit_val)[0]) if '板' in limit_val and re.findall(r'\d+', limit_val) else (
                int(limit_val) if limit_val.isdigit() else 0)

            industry = str(row.get('ths_hot_concept', row.get('industry', '未知')))
            if industry == 'nan' or not industry: industry = '未知'

            circ_mv = parse_chinese_money(
                row.get('circ_mv', row.get('float_mv', row.get('流通市值', row.get('total_mv', 0)))))
            if circ_mv > 100000000: circ_mv /= 10000.0

            amt_raw = str(row.get('amount', row.get('成交额', row.get('昨日成交额', 0))))
            yest_amt = parse_chinese_money(amt_raw)
            if yest_amt > 100000000:
                yest_amt /= 10000.0
            elif amt_raw.replace('.', '').isdigit() and yest_amt > 100000 and '亿' not in amt_raw:
                yest_amt /= 10.0

            history_map[code] = {'circ_mv': circ_mv, 'yest_amt': yest_amt, 'yest_pct': yest_pct, 'boards': boards,
                                 'industry': industry}
    except Exception as e:
        print(f"{Fore.RED}❌ 解析 strategy_pool.csv 失败: {e}{Style.RESET_ALL}")

    return history_map, pool_map


def load_manual_focus():
    if not os.path.exists(MANUAL_FOCUS_PATH): return set()
    s = set()
    try:
        with open(MANUAL_FOCUS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                for p in line.split(): s.add(p.zfill(6) if p.isdigit() else p)
    except:
        pass
    return s


# ================= 2. 获取实时数据 =================
def get_live_data():
    auction_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'call_auction')
    if not os.path.exists(auction_dir): return pd.DataFrame()

    valid_files = [os.path.join(auction_dir, f) for f in os.listdir(auction_dir) if
                   f.endswith('.txt') or f.endswith('.csv')]
    if not valid_files: return pd.DataFrame()

    latest_file = max(valid_files, key=os.path.getmtime)
    print(f"{Fore.CYAN}📂 [2/4] 加载竞价文件: {os.path.basename(latest_file)}...{Style.RESET_ALL}")

    try:
        content = ""
        for enc in ['gbk', 'utf-8', 'gb18030', 'utf-16']:
            try:
                with open(latest_file, 'r', encoding=enc) as f:
                    content = f.read()
                if content: break
            except:
                continue

        lines = content.strip().split('\n')
        if len(lines) < 2: return pd.DataFrame()

        headers = [h.strip() for h in lines[0].split('\t') if h.strip()]
        data_list = [{h: (parts[i] if i < len(parts) else "") for i, h in enumerate(headers)}
                     for line in lines[1:] if line.strip() for parts in
                     [[p.strip() for p in line.strip('\r\n').split('\t') if p.strip()]] if parts]

        df = pd.DataFrame(data_list)
        code_col = '代码' if '代码' in df.columns else ('code' if 'code' in df.columns else None)
        if code_col and not df.empty:
            df['code'] = df[code_col].apply(lambda x: re.sub(r'\D', '', str(x)).zfill(6))
            df['name'] = df.get('名称', df.get('name', '未知'))
            return df
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 读取异常: {e}{Style.RESET_ALL}")
    return pd.DataFrame()


# ================= 3. 核心策略判定 (融合板块小弟一字反推) =================
def analyze_stock(row, history_info, pool_map, is_holding, is_focus, limit_up_concepts):
    code = row.get('code')
    name = row.get('name', '')

    # 1. 垃圾股防雷：过滤ST (除非是你的持仓)
    if 'ST' in name.upper() and not is_holding:
        return {'fail_reason': '过滤ST股'}

    try:
        auc_pct_raw = row.get('竞价涨幅', '')
        if not auc_pct_raw or pd.isna(auc_pct_raw) or auc_pct_raw == '--':
            auc_pct_raw = row.get('涨幅', row.get('open_pct', 0))
        open_pct = parse_pct(auc_pct_raw)
        real_pct = parse_pct(row.get('涨幅', row.get('pct', 0)))

        auc_amt = parse_chinese_money(row.get('竞价金额', row.get('auc_amt', 0)))
        last_amt_export = parse_chinese_money(row.get('昨日成交额', row.get('昨成交', 0)))
        circ_mv_export = parse_chinese_money(row.get('流通市值', 0))
        boards_export = str(row.get('连续涨停天数', '')).strip()
        yest_pct_export = parse_pct(row.get('昨日涨跌幅', row.get('昨幅', 0)))
    except Exception as e:
        return {'fail_reason': f'数据解析异常'}

    info = history_info.get(code, {})
    circ_mv = circ_mv_export if circ_mv_export > 0 else info.get('circ_mv', 0)
    last_amt = last_amt_export if last_amt_export > 0 else info.get('yest_amt', 0)
    yest_pct = yest_pct_export if yest_pct_export != 0 else info.get('yest_pct', 0)
    boards = int(boards_export) if boards_export.isdigit() else info.get('boards', 0)
    industry = info.get('industry', '未知')
    pool_tag = pool_map.get(code, "")

    # 2. 动态资金门槛过滤 (核心降噪)
    min_auc = 1000  # 普通股竞价不到1000万直接过滤(防止骗炮)
    if pool_tag: min_auc = 500  # 底库股门槛放宽到 500万
    if is_focus: min_auc = 300  # 手动关注门槛 300万
    if is_holding: min_auc = 0  # 持仓无视门槛

    if auc_amt < min_auc:
        return {'fail_reason': f'竞价弱势({auc_amt:.0f}万<{min_auc}万)'}

    # 3. 置信度打分系统
    score = 60
    decision = "观察"
    fail_msg = ""

    # -- 💣 防雷雷达：巨量滞涨派发陷阱 --
    is_distribution_trap = (auc_amt >= 5000) and (-3.0 <= open_pct < 3.0) and (last_amt >= 10000)

    # -- 弱转强核心战法判定 --
    is_weak_to_strong = (yest_pct < 4.0 and open_pct > 1.5 and auc_amt > 1500)
    if "烂板" in pool_tag or "分歧" in pool_tag:
        if open_pct > 0.0 and auc_amt > 1000:
            is_weak_to_strong = True

    # -- 🔥 L大模式：老龙破局判定 (核心联动逻辑) --
    # 解析当前个股的概念集合
    my_concepts = set([c.strip() for c in re.split(r'[/+,-]', industry) if c.strip()])
    # 判断是否与今天一字板的概念有交集（有小弟助攻）
    has_limit_up_brother = bool(my_concepts.intersection(limit_up_concepts))

    # 老龙横盘标的，同板块有小弟一字板，且自身高开有承接
    is_old_dragon_breakout = ("[老龙横盘]" in pool_tag) and has_limit_up_brother and (open_pct >= 0.0) and (
                auc_amt > 1000)

    # ---------- 核心决策树 (优先级由高到低) ----------
    if open_pct > 9.8:
        score = 80 if is_focus else 0
        decision = f"{Fore.BLUE}🔒 一字板加速{Style.RESET_ALL}"
    elif is_distribution_trap:
        decision = f"{Fore.RED}💣 巨量滞涨(派发大坑/快跑){Style.RESET_ALL}"
        score = 30
    elif is_old_dragon_breakout:
        decision = f"{Fore.RED}🐉 老龙反推(小弟一字助攻){Style.RESET_ALL}"
        score = 98  # 极高分，置顶显示
    elif is_weak_to_strong:
        decision = f"{Fore.MAGENTA}🚀 弱转强抢筹{Style.RESET_ALL}"
        score = 95
    elif "主力" in pool_tag or "抢筹" in pool_tag:
        if 0 < open_pct < 5.0:
            decision = f"{Fore.RED}🔥 主力共振{Style.RESET_ALL}"
            score = 90
    elif open_pct <= -5.0 and ("低吸" in pool_tag or "趋势" in pool_tag):
        decision = f"{Fore.GREEN}✅ 趋势深水回踩{Style.RESET_ALL}"
        score = 85
    elif 5.0 < open_pct < 9.8:
        decision = f"{Fore.YELLOW}⚠️ 高开缩量风险{Style.RESET_ALL}"
        score = 60

        # 加分项
    if pool_tag: score += 10
    if is_focus: score += 15
    if is_holding: score = 100  # 持仓无视分数，强制显现

    if code in pool_map and pool_tag:
        decision += f" {Back.MAGENTA}{Fore.WHITE}[{pool_tag}]{Style.RESET_ALL}"

    return {
        'code': code, 'name': name, 'score': score, 'decision': decision,
        'open_pct': open_pct, 'real_pct': real_pct, 'auc': auc_amt, 'yest_pct': yest_pct,
        'boards': boards, 'circ_mv': circ_mv, 'tag': pool_tag, 'sector_info': industry,
        'last_amt': last_amt, 'is_holding': is_holding, 'is_focus': is_focus
    }


def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (极简防雷老龙版 v7.2) {Style.RESET_ALL}")
    print("=" * 145)

    history_map, pool_map = load_tushare_pool_and_history()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    live_df = get_live_data()
    if live_df.empty: return

    # ======================================================================
    # 🌟 关键新增：扫描全市场竞价，提取领涨板块（一字板小弟）基因
    # ======================================================================
    print(f"{Fore.CYAN}⚙️ [3/4] 正在扫描全市场一字板，提取领涨板块基因...{Style.RESET_ALL}")
    limit_up_concepts = set()
    for _, row in live_df.iterrows():
        auc_pct_raw = row.get('竞价涨幅', row.get('涨幅', row.get('open_pct', 0)))
        open_pct = parse_pct(auc_pct_raw)
        if open_pct > 9.8:
            code = clean_code(row.get('代码', row.get('code', '')))
            info = history_map.get(code, {})
            industry = info.get('industry', '未知')
            if industry != '未知':
                # 将复合概念切分为独立词条，如 "特高压/智能电网" -> ["特高压", "智能电网"]
                for c in re.split(r'[/+,-]', industry):
                    if c.strip():
                        limit_up_concepts.add(c.strip())

    print(f"   └── 共捕捉到 {Fore.RED}{len(limit_up_concepts)}{Style.RESET_ALL} 个涨停强势概念")

    # ======================================================================
    print(f"{Fore.CYAN}⚙️ [4/4] 正在执行【除杂降噪】与【老龙反推联动分析】...{Style.RESET_ALL}")

    results = []
    seen_codes = set()
    filter_stats = {}

    for _, row in live_df.iterrows():
        code = clean_code(row.get('代码', row.get('code', '')))
        if not code or code in seen_codes: continue
        seen_codes.add(code)

        is_holding = code in holdings
        is_focus = code in manual_focus or str(row.get('名称', '')) in manual_focus
        is_in_pool = code in pool_map

        if not (is_holding or is_focus or is_in_pool):
            filter_stats["不在监控池"] = filter_stats.get("不在监控池", 0) + 1
            continue

        # 将整理好的强势概念集合传给处理函数
        res = analyze_stock(row, history_map, pool_map, is_holding, is_focus, limit_up_concepts)

        if 'fail_reason' in res:
            reason = res['fail_reason']
            filter_stats[reason] = filter_stats.get(reason, 0) + 1
        else:
            results.append(res)

    # 🚀 多重维度复合排序：
    # 1. 持仓必顶 (True在前)
    # 2. 核心关注必顶 (True在前)
    # 3. AI 置信分数 (倒序，越高越前)
    # 4. 竞价金额大小 (倒序，越大越前，资金为王)
    results.sort(key=lambda x: (
        x['is_holding'],
        x['is_focus'],
        x['score'],
        x['auc']
    ), reverse=True)

    print("\n" + "=" * 145)
    print(f"{Fore.YELLOW}🛡️ 策略流水线拦截明细：{Style.RESET_ALL}")
    for reason, count in filter_stats.items():
        if count > 0: print(f"  - {reason}: 拦截了 {count} 只无效标的")

    print("=" * 145)
    print(f"📊 精锐监控池 | 扫描总数: {len(live_df)} | {Fore.GREEN}高度聚焦老龙破局、弱转强与持仓防雷{Style.RESET_ALL}")
    print(
        f"{'代码':<8} {'名称':<6} {'竞价%':>6} {'现幅%':>6} {'昨幅%':>6}   {'竞价额':<8} {'连板':<4} {'市值':<8} {'昨额':<8} {'所属行业'}  {'AI决策与流向标签'}")
    print("-" * 155)

    display_count = 0
    for item in results:
        # 🔪 核心过滤：非持仓、非关注的票，置信分必须 >= 85 才配显示
        if not item['is_holding'] and not item['is_focus'] and item['score'] < 85:
            continue

        display_count += 1

        c_open = Fore.RED if item['open_pct'] > 0 else (Fore.GREEN if item['open_pct'] < 0 else Fore.WHITE)
        c_real = Fore.RED if item['real_pct'] > 0 else (Fore.GREEN if item['real_pct'] < 0 else Fore.WHITE)
        c_yest = Fore.RED if item['yest_pct'] > 0 else (Fore.GREEN if item['yest_pct'] < 0 else Fore.WHITE)

        auc_str = f"{int(item['auc'])}万"
        yest_amt_val = item['last_amt']
        yest_str = "未知" if yest_amt_val == 0 else (
            f"{yest_amt_val / 10000:.1f}亿" if yest_amt_val > 10000 else f"{int(yest_amt_val)}万")
        boards = item['boards']
        boards_str = f"{Fore.RED}{boards}板{Style.RESET_ALL}" if boards >= 2 else ""
        mv_val = item['circ_mv']
        mv_str = "未知" if mv_val == 0 else (f"{mv_val / 10000.0:.1f}亿" if mv_val > 10000 else f"{int(mv_val)}万")

        # 标注特殊身份
        prefix_icon = ""
        if item['is_holding']:
            prefix_icon = f"{Back.RED}{Fore.WHITE} 💼持仓 {Style.RESET_ALL} "
        elif item['is_focus']:
            prefix_icon = f"{Back.YELLOW}{Fore.BLACK} ⭐关注 {Style.RESET_ALL} "

        print(
            f"{item['code']:<8} {item['name']:<6} "
            f"{c_open}{item['open_pct']:>6.2f}{Style.RESET_ALL}  "
            f"{c_real}{item['real_pct']:>6.2f}{Style.RESET_ALL}  "
            f"{c_yest}{item['yest_pct']:>6.2f}{Style.RESET_ALL}   "
            f"{Fore.YELLOW}{auc_str:<8}{Style.RESET_ALL} "
            f"{boards_str:<5} {mv_str:<8} {yest_str:<8} "
            f"{item['sector_info']:<12} {prefix_icon}{item['decision']}"
        )

    if display_count == 0:
        print(f"{Fore.YELLOW}当前无符合极端条件的精锐标的，请空仓等待或只处理持仓。{Style.RESET_ALL}")

    print("=" * 145)
    print(f"💡 最终仅显示 {Fore.GREEN}{display_count}{Style.RESET_ALL} 只高价值标的，方便极速决策！")


if __name__ == "__main__":
    main()