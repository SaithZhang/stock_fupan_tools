# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (架构重构微服务版 v8.1)
# ==============================================================================
import pandas as pd
import os
import re
import sys
import io
from colorama import init, Fore, Style, Back

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# 路径配置
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import load_holdings
from src.monitors.auction.models import LiveStockContext
from src.monitors.auction.engine import AuctionScreenerEngine

MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')

# ----------------- 数据解析工具 -----------------
def clean_code(val): return re.sub(r'\D', '', str(val)).zfill(6)

def parse_chinese_money(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).strip()
    if not val_str or val_str == '--' or val_str.lower() == 'nan': return 0.0
    try:
        if '亿' in val_str: return float(val_str.replace('亿', '').replace('万', '').replace('+', '').strip()) * 10000.0
        elif '万' in val_str: return float(val_str.replace('万', '').replace('+', '').strip())
        else: return float(val_str.replace('+', ''))
    except: return 0.0

def parse_pct(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace('%', '').replace('+', '')
    if not val_str or val_str == '--' or val_str.lower() == 'nan': return 0.0
    try: return float(val_str)
    except: return 0.0

# ----------------- 数据加载层 -----------------
def load_tushare_pool_and_history():
    print(f"{Fore.CYAN}📂 [1/4] 加载 Tushare 盘后底库...{Style.RESET_ALL}")
    pool_path = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')
    history_map, pool_map = {}, {}
    if not os.path.exists(pool_path): return history_map, pool_map
    try:
        df = pd.read_csv(pool_path, dtype=str)
        df.columns = df.columns.str.strip()
        for _, row in df.iterrows():
            code = clean_code(row.get('code', row.get('ts_code', row.get('代码', ''))))
            if not code: continue
            tag = str(row.get('tag', '')).strip()
            if tag and tag.lower() != 'nan': pool_map[code] = tag
            yest_pct = parse_pct(row.get('pct_chg', row.get('today_pct', 0)))
            lv = str(row.get('limit_status', row.get('连板数', '0')))
            boards = int(re.findall(r'\d+', lv)[0]) if '板' in lv and re.findall(r'\d+', lv) else (int(lv) if lv.isdigit() else 0)
            industry = str(row.get('ths_hot_concept', row.get('industry', '未知')))
            circ_mv = parse_chinese_money(row.get('circ_mv', row.get('流通市值', 0)))
            if circ_mv > 100000000: circ_mv /= 10000.0
            yest_amt = parse_chinese_money(row.get('amount', row.get('昨日成交额', 0)))
            if yest_amt > 100000000: yest_amt /= 10000.0
            history_map[code] = {'circ_mv': circ_mv, 'yest_amt': yest_amt, 'yest_pct': yest_pct, 'boards': boards, 'industry': industry}
    except: pass
    return history_map, pool_map

def load_manual_focus():
    if not os.path.exists(MANUAL_FOCUS_PATH): return set()
    s = set()
    try:
        with open(MANUAL_FOCUS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('#'): [s.add(p.zfill(6) if p.isdigit() else p) for p in line.split()]
    except: pass
    return s

def get_live_data():
    auction_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'call_auction')
    if not os.path.exists(auction_dir): return pd.DataFrame()
    valid_files = [os.path.join(auction_dir, f) for f in os.listdir(auction_dir) if f.endswith('.txt') or f.endswith('.csv')]
    if not valid_files: return pd.DataFrame()
    latest_file = max(valid_files, key=os.path.getmtime)
    print(f"{Fore.CYAN}📂 [2/4] 加载竞价文件: {os.path.basename(latest_file)}...{Style.RESET_ALL}")
    try:
        content = ""
        for enc in ['gbk', 'utf-8', 'gb18030']:
            try:
                with open(latest_file, 'r', encoding=enc) as f: content = f.read()
                if content: break
            except: continue
        lines = content.strip().split('\n')
        if len(lines) < 2: return pd.DataFrame()
        headers = [h.strip() for h in lines[0].split('\t') if h.strip()]
        data_list = [{h: (parts[i] if i < len(parts) else "") for i, h in enumerate(headers)}
                     for line in lines[1:] if line.strip() for parts in [[p.strip() for p in line.strip('\r\n').split('\t') if p.strip()]] if parts]
        df = pd.DataFrame(data_list)
        code_col = '代码' if '代码' in df.columns else ('code' if 'code' in df.columns else None)
        if code_col and not df.empty:
            df['code'] = df[code_col].apply(lambda x: re.sub(r'\D', '', str(x)).zfill(6))
            df['name'] = df.get('名称', df.get('name', '未知'))
            return df
    except: pass
    return pd.DataFrame()

# ----------------- 主程序入口 -----------------
def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (流水线微服务版 v8.1) {Style.RESET_ALL}")
    print("=" * 145)

    history_map, pool_map = load_tushare_pool_and_history()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    live_df = get_live_data()
    if live_df.empty: return

    print(f"{Fore.CYAN}⚙️ [3/4] 扫描全市场一字板基因...{Style.RESET_ALL}")
    limit_up_concepts = set()
    for _, row in live_df.iterrows():
        auc_pct_raw = row.get('竞价涨幅', row.get('涨幅', row.get('open_pct', 0)))
        if parse_pct(auc_pct_raw) > 9.8:
            info = history_map.get(clean_code(row.get('代码', '')), {})
            for c in re.split(r'[/+,-]', info.get('industry', '')):
                if c.strip() and c.strip() != '未知': limit_up_concepts.add(c.strip())
    print(f"   └── 共捕捉 {Fore.RED}{len(limit_up_concepts)}{Style.RESET_ALL} 个强势概念")

    print(f"{Fore.CYAN}⚙️ [4/4] 引擎点火: 正在流水分发与战法评估...{Style.RESET_ALL}")
    engine = AuctionScreenerEngine()
    results, filter_stats = [], {}
    seen_codes = set()

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

        info = history_map.get(code, {})
        # 构建不可变的上下文
        ctx = LiveStockContext(
            code=code, name=row.get('name', ''),
            open_pct=parse_pct(row.get('竞价涨幅', row.get('涨幅', 0))),
            real_pct=parse_pct(row.get('涨幅', 0)),
            auc_amt=parse_chinese_money(row.get('竞价金额', 0)),
            yest_pct=info.get('yest_pct', parse_pct(row.get('昨日涨跌幅', 0))),
            last_amt=info.get('yest_amt', parse_chinese_money(row.get('昨日成交额', 0))),
            circ_mv=info.get('circ_mv', parse_chinese_money(row.get('流通市值', 0))),
            boards=info.get('boards', 0), industry=info.get('industry', '未知'),
            pool_tag=pool_map.get(code, ""), is_holding=is_holding, is_focus=is_focus,
            limit_up_concepts=limit_up_concepts
        )

        res = engine.evaluate(ctx)
        if 'fail_reason' in res: filter_stats[res['fail_reason']] = filter_stats.get(res['fail_reason'], 0) + 1
        else: results.append(res)

    results.sort(key=lambda x: (x['is_holding'], x['is_focus'], x['score'], x['auc']), reverse=True)

    print("\n" + "=" * 145)
    for reason, count in filter_stats.items():
        if count > 0: print(f"  - {reason}: 拦截了 {count} 只无效标的")

    print("=" * 145)
    print(f"📊 战法精锐池 | 扫描总数: {len(live_df)} | {Fore.GREEN}聚焦老龙破局与持仓防雷{Style.RESET_ALL}")
    print(f"{'代码':<8} {'名称':<6} {'竞价%':>6} {'现幅%':>6} {'昨幅%':>6}   {'竞价额':<8} {'连板':<4} {'市值':<8} {'昨额':<8} {'所属行业'}  {'AI决策与流向标签'}")
    print("-" * 155)

    # 1. 表头增加“(占比)”的空间
    print(
        f"{'代码':<8} {'名称':<6} {'竞价%':>6} {'现幅%':>6} {'昨幅%':>6}   {'竞价额(占比)':<14} {'连板':<4} {'市值':<8} {'昨额':<8} {'所属行业'}  {'AI决策与流向标签'}")
    print("-" * 155)

    display_count = 0
    for item in results:
        if not item['is_holding'] and not item['is_focus'] and item['score'] < 85: continue
        display_count += 1
        c_open = Fore.RED if item['open_pct'] > 0 else (Fore.GREEN if item['open_pct'] < 0 else Fore.WHITE)
        c_real = Fore.RED if item['real_pct'] > 0 else (Fore.GREEN if item['real_pct'] < 0 else Fore.WHITE)
        c_yest = Fore.RED if item['yest_pct'] > 0 else (Fore.GREEN if item['yest_pct'] < 0 else Fore.WHITE)

        # 计算竞价占昨额的比率 (爆量比)
        auc_ratio = (item['auc'] / item['last_amt'] * 100) if item['last_amt'] > 0 else 0
        ratio_color = Fore.RED if auc_ratio >= 5.0 else (Fore.YELLOW if auc_ratio >= 2.0 else Style.RESET_ALL)
        auc_ratio_str = f"{ratio_color}[{auc_ratio:>4.1f}%]{Style.RESET_ALL}"

        auc_str = f"{int(item['auc'])}万"

        # 2. 将 auc_str 和 auc_ratio_str 组合在一起
        combined_auc = f"{Fore.YELLOW}{auc_str:<6}{Style.RESET_ALL} {auc_ratio_str}"

        yest_str = f"{item['last_amt'] / 10000:.1f}亿" if item['last_amt'] > 10000 else f"{int(item['last_amt'])}万"
        boards_str = f"{Fore.RED}{item['boards']}板{Style.RESET_ALL}" if item['boards'] >= 2 else ""
        mv_str = f"{item['circ_mv'] / 10000.0:.1f}亿" if item['circ_mv'] > 10000 else f"{int(item['circ_mv'])}万"
        prefix = f"{Back.RED}{Fore.WHITE} 💼持仓 {Style.RESET_ALL} " if item['is_holding'] else (
            f"{Back.YELLOW}{Fore.BLACK} ⭐关注 {Style.RESET_ALL} " if item['is_focus'] else "")

        # 3. 打印时填入 combined_auc，对齐格式
        print(
            f"{item['code']:<8} {item['name']:<6} {c_open}{item['open_pct']:>6.2f}{Style.RESET_ALL}  {c_real}{item['real_pct']:>6.2f}{Style.RESET_ALL}  {c_yest}{item['yest_pct']:>6.2f}{Style.RESET_ALL}   {combined_auc:<25} {boards_str:<5} {mv_str:<8} {yest_str:<8} {item['sector_info']:<12} {prefix}{item['decision']}")

if __name__ == "__main__":
    main()