# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py)
# v6.0 盘后回测与盘中自适应强化版
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


# ================= 1. 加载 Tushare 盘后底库与策略池 =================
def load_tushare_pool_and_history():
    print(f"{Fore.CYAN}📂 [1/3] 正在加载 Tushare 盘后底库 (strategy_pool.csv)...{Style.RESET_ALL}")
    pool_path = os.path.join(PROJECT_ROOT, 'data', 'output', 'strategy_pool.csv')

    history_map = {}
    pool_map = {}

    if not os.path.exists(pool_path):
        print(f"{Fore.RED}❌ 未找到 Tushare 底库: {pool_path}{Style.RESET_ALL}")
        return history_map, pool_map

    try:
        df = pd.read_csv(pool_path, dtype=str)
        df.columns = df.columns.str.strip()

        for _, row in df.iterrows():
            code_raw = row.get('code', row.get('ts_code', row.get('代码', '')))
            code = clean_code(code_raw)
            if not code: continue

            tag = str(row.get('tag', row.get('策略标签', ''))).strip()
            if tag.lower() == 'nan': tag = ""
            if tag: pool_map[code] = tag

            # 💡 精准映射昨天的涨幅 (覆盖 Tushare 的多种字段变体)
            pct_val = row.get('pct_chg', row.get('涨跌幅', row.get('pct', row.get('today_pct', 0))))
            yest_pct = parse_pct(pct_val)

            limit_val = str(row.get('limit_status', row.get('连板数', row.get('连板高度', '0'))))
            boards = 0
            if '板' in limit_val:
                nums = re.findall(r'\d+', limit_val)
                if nums: boards = int(nums[0])
            elif limit_val.isdigit():
                boards = int(limit_val)

            industry = str(row.get('ths_hot_concept', row.get('industry', '未知')))
            if industry == 'nan' or not industry: industry = '未知'

            circ_mv = parse_chinese_money(
                row.get('circ_mv', row.get('float_mv', row.get('流通市值', row.get('total_mv', row.get('总市值', 0))))))
            if circ_mv > 100000000:
                circ_mv = circ_mv / 10000.0

            amt_raw = str(row.get('amount', row.get('成交额', row.get('昨日成交额', 0))))
            yest_amt = parse_chinese_money(amt_raw)
            if yest_amt > 100000000:
                yest_amt = yest_amt / 10000.0
            elif amt_raw.replace('.', '').isdigit() and yest_amt > 100000 and '亿' not in amt_raw:
                yest_amt = yest_amt / 10.0

            history_map[code] = {
                'circ_mv': circ_mv,
                'yest_amt': yest_amt,
                'yest_pct': yest_pct,
                'boards': boards,
                'industry': industry
            }

        print(f"✅ Tushare 底库与策略池加载完成，共载入 {len(history_map)} 只标的")
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
def load_call_auction_data_from_file():
    auction_dir = os.path.join(PROJECT_ROOT, 'data', 'input', 'call_auction')
    if not os.path.exists(auction_dir):
        return None

    valid_files = [os.path.join(auction_dir, f) for f in os.listdir(auction_dir) if
                   f.endswith('.txt') or f.endswith('.csv')]
    if not valid_files: return None

    latest_file = max(valid_files, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    print(f"{Fore.CYAN}📂 [2A/3] 检测到本地竞价文件: {filename}，启动非空序列锚定解析...{Style.RESET_ALL}")

    try:
        content = ""
        for enc in ['gbk', 'utf-8', 'gb18030', 'utf-16']:
            try:
                with open(latest_file, 'r', encoding=enc) as f:
                    content = f.read()
                if content: break
            except:
                continue

        if not content:
            print(f"{Fore.RED}❌ 文件读取失败，编码不匹配。{Style.RESET_ALL}")
            return None

        lines = content.strip().split('\n')
        if len(lines) < 2: return None

        headers = [h.strip() for h in lines[0].split('\t') if h.strip()]

        data_list = []
        for line in lines[1:]:
            line = line.strip('\r\n')
            if not line: continue

            parts = [p.strip() for p in line.split('\t') if p.strip()]
            if not parts: continue

            row_dict = {}
            for i, h in enumerate(headers):
                row_dict[h] = parts[i] if i < len(parts) else ""

            data_list.append(row_dict)

        df = pd.DataFrame(data_list)

        code_col = '代码' if '代码' in df.columns else ('code' if 'code' in df.columns else None)
        if code_col and not df.empty:
            print(f"✅ 从 {filename} 成功加载 {len(df)} 条竞价数据 (适配最新实时列头！)")
            df['code'] = df[code_col].apply(lambda x: re.sub(r'\D', '', str(x)).zfill(6))
            df['name'] = df.get('名称', df.get('name', '未知'))
            return df
        else:
            print(f"{Fore.YELLOW}⚠️ 竞价文件解析异常：未找到[代码]列。{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ 读取 {filename} 异常: {e}{Style.RESET_ALL}")

    return None


def get_live_data():
    local_df = load_call_auction_data_from_file()
    if local_df is not None and not local_df.empty: return local_df
    return pd.DataFrame()


# ================= 3. 策略判定 =================
def analyze_stock(row, history_info, pool_map):
    code = row.get('code')
    name = row.get('name')

    try:
        # 💡 逻辑穿透：盘后回测时，`竞价涨幅`才是早上9:25的信号，若无则降维取`涨幅`
        auc_pct_raw = row.get('竞价涨幅', '')
        if not auc_pct_raw or pd.isna(auc_pct_raw) or auc_pct_raw == '--':
            auc_pct_raw = row.get('涨幅', row.get('open_pct', 0))
        open_pct = parse_pct(auc_pct_raw)

        # 💡 `现幅%` 强制锚定 `涨幅` (盘后回测时，这就是全天收盘的最终涨幅)
        real_pct = parse_pct(row.get('涨幅', row.get('pct', 0)))

        # 💡 优先抓取新导出的金额及市值维度
        auc_amt = parse_chinese_money(row.get('竞价金额', row.get('auc_amt', 0)))
        last_amt_export = parse_chinese_money(row.get('昨日成交额', row.get('昨成交', row.get('last_amt', 0))))
        circ_mv_export = parse_chinese_money(row.get('流通市值', 0))
        boards_export = str(row.get('连续涨停天数', '')).strip()
        yest_pct_export = parse_pct(row.get('昨日涨跌幅', row.get('昨幅', 0)))
    except Exception as e:
        return {'fail_reason': f'数据解析异常: {e}'}

    info = history_info.get(code, {})

    # 优先使用实时表头的数据，若无则兜底 Tushare 底库
    circ_mv = circ_mv_export if circ_mv_export > 0 else info.get('circ_mv', 0)
    last_amt = last_amt_export if last_amt_export > 0 else info.get('yest_amt', 0)

    yest_pct = yest_pct_export if yest_pct_export != 0 else info.get('yest_pct', 0)

    boards = 0
    if boards_export and boards_export.isdigit():
        boards = int(boards_export)
    else:
        boards = info.get('boards', 0)

    industry = info.get('industry', '未知')

    ratio_yest = (auc_amt / last_amt * 100) if last_amt > 0 else 0
    ratio_mv = (auc_amt / circ_mv * 100) if circ_mv > 0 else 0

    score = 60
    decision = "观察"
    fail_msg = ""
    pool_tag = pool_map.get(code, "")

    min_auc = 300
    if code in pool_map: min_auc = 0
    if auc_amt < min_auc:
        return {'fail_reason': f'竞价金额不足({auc_amt:.1f}万<300万)'}

    if open_pct > 9.8:
        score = 0
        if code in pool_map: score = 90
        return {
            'code': code, 'name': name, 'score': score, 'decision': f"{Fore.BLUE}一字板{Style.RESET_ALL}",
            'open_pct': open_pct, 'real_pct': real_pct, 'auc': auc_amt, 'yest_pct': yest_pct, 'boards': boards,
            'r_mv': ratio_mv, 'circ_mv': circ_mv, 'sector_info': industry, 'last_amt': last_amt, 'tag': pool_tag
        }

    if "主力" in pool_tag or "抢筹" in pool_tag:
        if 0 < open_pct < 5.0:
            decision = f"{Fore.RED}🔥 主力抢筹共振{Style.RESET_ALL}"
            score = 92
        elif open_pct < 0:
            decision = f"{Fore.GREEN}✅ 资金底背离低吸{Style.RESET_ALL}"
            score = 88
    elif "连板" in pool_tag or "龙头" in pool_tag:
        if open_pct < 3.0 and (ratio_mv > 0.8 or (circ_mv == 0 and auc_amt > 1000)):
            decision = f"{Fore.MAGENTA}★ 龙头弱转强{Style.RESET_ALL}"
            score = 95
        else:
            fail_msg = "弱转强量能不足"
    elif open_pct <= -5.0:
        if "低吸" in pool_tag or "趋势" in pool_tag:
            decision = f"{Fore.GREEN}✅ 趋势回踩{Style.RESET_ALL}"
            score = 85
        else:
            fail_msg = f"深水({open_pct}%)不符合低吸池"
    else:
        if 5.0 < open_pct < 9.8:
            decision = f"{Fore.YELLOW}⚠️ 高开风险{Style.RESET_ALL}"
            score = 60

    if code in pool_map:
        if score < 80: score += 10
        display_tag = pool_tag
        decision += f" {Back.MAGENTA}{Fore.WHITE} [{display_tag}] {Style.RESET_ALL}"
        if fail_msg:
            decision = f"{Fore.YELLOW}{fail_msg} [{display_tag}]{Style.RESET_ALL}"
            score = 70
            fail_msg = ""

    if fail_msg: return {'fail_reason': f'策略未通过: {fail_msg}'}
    if score < 60 and not pool_tag: return {'fail_reason': f'综合打分过低({score}分)'}

    return {
        'code': code, 'name': name, 'score': score, 'decision': decision,
        'open_pct': open_pct, 'real_pct': real_pct, 'auc': auc_amt, 'r_mv': ratio_mv, 'yest_pct': yest_pct,
        'boards': boards, 'circ_mv': circ_mv, 'tag': pool_tag, 'sector_info': industry, 'last_amt': last_amt
    }


def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (Tushare 流水线驱动版) {Style.RESET_ALL}")
    print("=" * 120)

    history_map, pool_map = load_tushare_pool_and_history()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    valid_codes = set(pool_map.keys()) | set(holdings.keys())
    for item in manual_focus:
        if item.isdigit(): valid_codes.add(item)

    live_df = get_live_data()
    if live_df.empty: return

    print(f"{Fore.CYAN}⚙️ [3/3] 正在执行策略流水线穿透分析...{Style.RESET_ALL}")

    results = []
    seen_codes = set()
    filter_stats = {}

    for _, row in live_df.iterrows():
        code = clean_code(row.get('代码', row.get('code', '')))
        if not code or code in seen_codes: continue
        seen_codes.add(code)

        is_target = code in valid_codes or str(row.get('名称', row.get('name', ''))) in manual_focus
        if not is_target:
            filter_stats["不在策略池(Tushare 过滤)"] = filter_stats.get("不在策略池(Tushare 过滤)", 0) + 1
            continue

        res = analyze_stock(row, history_map, pool_map)

        if res:
            if 'fail_reason' in res:
                reason = res['fail_reason']
                if "金额不足" in reason:
                    filter_stats["竞价金额不足(低于300万)"] = filter_stats.get("竞价金额不足(低于300万)", 0) + 1
                elif "策略未通过" in reason:
                    filter_stats["未满足买点逻辑"] = filter_stats.get("未满足买点逻辑", 0) + 1
                else:
                    filter_stats[reason] = filter_stats.get(reason, 0) + 1
            else:
                results.append(res)

    results.sort(key=lambda x: (x['score'], x['open_pct']), reverse=True)

    print("\n" + "=" * 145)
    print(f"{Fore.YELLOW}🛡️ 策略流水线拦截明细：{Style.RESET_ALL}")
    for reason, count in filter_stats.items():
        if count > 0: print(f"  - {reason}: 过滤了 {count} 只标的")

    print("=" * 145)
    print(f"📊 实时监控池 | 扫描总数: {len(live_df)} | 命中策略: {len(results)}")

    print(
        f"{'代码':<8} {'名称':<6} {'竞价%':>6} {'现幅%':>6} {'昨幅%':>6}   {'竞价额':<8} {'连板':<4} {'市值':<8} {'昨额':<8} {'所属行业'}  {'AI决策与流向标签'}")
    print("-" * 155)

    count = 0
    for item in results:
        if item['score'] < 40: continue
        count += 1

        c_open = Fore.RED if item['open_pct'] > 0 else (Fore.GREEN if item['open_pct'] < 0 else Fore.WHITE)
        real_pct = item.get('real_pct', 0.0)
        c_real = Fore.RED if real_pct > 0 else (Fore.GREEN if real_pct < 0 else Fore.WHITE)
        yest_pct = item.get('yest_pct', 0)
        c_yest = Fore.RED if yest_pct > 0 else (Fore.GREEN if yest_pct < 0 else Fore.WHITE)

        auc_str = f"{int(item['auc'])}万"

        yest_amt_val = item.get('last_amt', 0)
        yest_str = "未知" if yest_amt_val == 0 else (
            f"{yest_amt_val / 10000:.1f}亿" if yest_amt_val > 10000 else f"{int(yest_amt_val)}万")

        boards = item.get('boards', 0)
        boards_str = f"{Fore.RED}{boards}板{Style.RESET_ALL}" if boards >= 2 else ""

        mv_val = item.get('circ_mv', 0)
        mv_str = "未知" if mv_val == 0 else (f"{mv_val / 10000.0:.1f}亿" if mv_val > 10000 else f"{int(mv_val)}万")

        industry = item.get('sector_info', '未知')

        # 💡 在各列之间增加了明确的空格，杜绝数据粘连 (特别是昨幅% 与 竞价额 之间)
        print(
            f"{item['code']:<8} {item['name']:<6} "
            f"{c_open}{item['open_pct']:>6.2f}{Style.RESET_ALL}  "
            f"{c_real}{real_pct:>6.2f}{Style.RESET_ALL}  "
            f"{c_yest}{yest_pct:>6.2f}{Style.RESET_ALL}   "
            f"{Fore.YELLOW}{auc_str:<8}{Style.RESET_ALL} "
            f"{boards_str:<5} {mv_str:<8} {yest_str:<8} "
            f"{industry}  {item['decision']}"
        )

    if count == 0:
        print(f"{Fore.YELLOW}当前竞价无符合 Tushare 标签强共振标的。{Style.RESET_ALL}")
    print("=" * 145)


if __name__ == "__main__":
    main()