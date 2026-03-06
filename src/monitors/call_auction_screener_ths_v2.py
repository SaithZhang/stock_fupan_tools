# ==============================================================================
# 📌 F佬/Bo佬 智能盘中监控系统 (src\monitors\call_auction_screener.py)
# v8.0 流水线重构版 - (责任链拦截 + 策略模式打分，极简扩展)
# ==============================================================================
import pandas as pd
import os
import re
import sys
import io
import time
from dataclasses import dataclass
from typing import Tuple, Dict, List, Set
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


# ================= 🛠️ 工具函数 =================
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


# ================= 📦 领域模型 (Context) =================
@dataclass
class LiveStockContext:
    """盘中个股上下文，封装所有需要评估的数据，消灭散装变量"""
    code: str
    name: str
    open_pct: float
    real_pct: float
    auc_amt: float
    yest_pct: float
    last_amt: float
    circ_mv: float
    boards: int
    industry: str
    pool_tag: str
    is_holding: bool
    is_focus: bool
    limit_up_concepts: Set[str]  # 全局当日一字板概念集合

    @property
    def my_concepts(self) -> Set[str]:
        """解析自身的概念集合"""
        return set([c.strip() for c in re.split(r'[/+,-]', self.industry) if c.strip()])

    @property
    def has_limit_up_brother(self) -> bool:
        """判断是否有同概念小弟顶了一字板"""
        return bool(self.my_concepts.intersection(self.limit_up_concepts))


# ================= 🛡️ 责任链拦截器 (Filters) =================
class BaseFilter:
    def check(self, ctx: LiveStockContext) -> Tuple[bool, str]:
        raise NotImplementedError


class STFilter(BaseFilter):
    def check(self, ctx: LiveStockContext):
        if 'ST' in ctx.name.upper() and not ctx.is_holding:
            return False, '过滤ST股'
        return True, ""


class MinAuctionAmountFilter(BaseFilter):
    def check(self, ctx: LiveStockContext):
        min_auc = 1000  # 普通股门槛
        if ctx.pool_tag: min_auc = 500  # 底库股放宽
        if ctx.is_focus: min_auc = 300  # 关注股放宽
        if ctx.is_holding: min_auc = 0  # 持仓无视门槛

        if ctx.auc_amt < min_auc:
            return False, f'竞价弱势({ctx.auc_amt:.0f}万<{min_auc}万)'
        return True, ""


# ================= ⚔️ 战法策略引擎 (Strategies) =================
class BaseStrategy:
    def evaluate(self, ctx: LiveStockContext) -> Tuple[bool, int, str]:
        """返回: (是否命中, 基础得分, 决策标签)"""
        raise NotImplementedError


class OneLineBoardStrategy(BaseStrategy):
    """一字板加速过滤"""

    def evaluate(self, ctx):
        if ctx.open_pct > 9.8:
            score = 80 if ctx.is_focus else 0  # 买不到的不看，除非特别关注
            return True, score, f"{Fore.BLUE}🔒 一字板加速{Style.RESET_ALL}"
        return False, 0, ""


class DistributionTrapStrategy(BaseStrategy):
    """💣 防雷：巨量滞涨派发陷阱"""

    def evaluate(self, ctx):
        if ctx.auc_amt >= 5000 and -3.0 <= ctx.open_pct < 3.0 and ctx.last_amt >= 10000:
            return True, 30, f"{Fore.RED}💣 巨量滞涨(派发大坑/快跑){Style.RESET_ALL}"
        return False, 0, ""


class OldDragonBreakoutStrategy(BaseStrategy):
    """🐉 L大核心：老龙反推破局"""

    def evaluate(self, ctx):
        if "[老龙横盘]" in ctx.pool_tag and ctx.has_limit_up_brother:
            if ctx.open_pct >= 0.0 and ctx.auc_amt > 1000:
                return True, 98, f"{Fore.RED}🐉 老龙反推(小弟一字助攻){Style.RESET_ALL}"
        return False, 0, ""


class WeakToStrongStrategy(BaseStrategy):
    """🚀 核心：弱转强抢筹"""

    def evaluate(self, ctx):
        # 情况A：水下/微红高开爆量
        if ctx.yest_pct < 4.0 and ctx.open_pct > 1.5 and ctx.auc_amt > 1500:
            return True, 95, f"{Fore.MAGENTA}🚀 弱转强抢筹{Style.RESET_ALL}"
        # 情况B：前日烂板分歧，今日超预期
        if ("烂板" in ctx.pool_tag or "分歧" in ctx.pool_tag) and ctx.open_pct > 0.0 and ctx.auc_amt > 1000:
            return True, 95, f"{Fore.MAGENTA}🚀 弱转强(分歧转一致){Style.RESET_ALL}"
        return False, 0, ""


class MainForceResonanceStrategy(BaseStrategy):
    """🔥 主力抢筹共振"""

    def evaluate(self, ctx):
        if ("主力" in ctx.pool_tag or "抢筹" in ctx.pool_tag) and 0 < ctx.open_pct < 5.0:
            return True, 90, f"{Fore.RED}🔥 主力共振{Style.RESET_ALL}"
        return False, 0, ""


class TrendDipStrategy(BaseStrategy):
    """✅ 趋势深水回踩"""

    def evaluate(self, ctx):
        if ctx.open_pct <= -5.0 and ("低吸" in ctx.pool_tag or "趋势" in ctx.pool_tag):
            return True, 85, f"{Fore.GREEN}✅ 趋势深水回踩{Style.RESET_ALL}"
        return False, 0, ""


class HighOpenRiskStrategy(BaseStrategy):
    """⚠️ 高开缩量提示"""

    def evaluate(self, ctx):
        if 5.0 < ctx.open_pct < 9.8:
            return True, 60, f"{Fore.YELLOW}⚠️ 高开缩量风险{Style.RESET_ALL}"
        return False, 0, ""


# ================= 🏭 流水线引擎 =================
class AuctionScreenerEngine:
    def __init__(self):
        # 1. 注册拦截器 (一旦未通过，直接出局)
        self.filters: List[BaseFilter] = [
            STFilter(),
            MinAuctionAmountFilter()
        ]

        # 2. 注册战法策略 (严格按优先级先后排序！匹配即退出)
        self.strategies: List[BaseStrategy] = [
            OneLineBoardStrategy(),
            DistributionTrapStrategy(),  # 拦截陷阱优先级极高
            OldDragonBreakoutStrategy(),  # 核心战法
            WeakToStrongStrategy(),  # 核心战法
            MainForceResonanceStrategy(),
            TrendDipStrategy(),
            HighOpenRiskStrategy()
        ]

    def evaluate(self, ctx: LiveStockContext) -> Dict:
        """执行单只股票的流水分发"""
        # 第一阶段：黑名单拦截
        for f in self.filters:
            passed, reason = f.check(ctx)
            if not passed:
                return {'fail_reason': reason}

        # 第二阶段：策略引擎打分
        best_score = 60
        decision = "观察"

        for strategy in self.strategies:
            matched, score, desc = strategy.evaluate(ctx)
            if matched:
                best_score = score
                decision = desc
                break  # 命中高优先级策略，终止后续打分

        # 第三阶段：上下文加分项 (独立于战法)
        if ctx.pool_tag: best_score += 10
        if ctx.is_focus: best_score += 15
        if ctx.is_holding: best_score = 100  # 持仓无脑置顶

        if ctx.pool_tag:
            decision += f" {Back.MAGENTA}{Fore.WHITE}[{ctx.pool_tag}]{Style.RESET_ALL}"

        # 组装返回结果
        return {
            'code': ctx.code, 'name': ctx.name, 'score': best_score, 'decision': decision,
            'open_pct': ctx.open_pct, 'real_pct': ctx.real_pct, 'auc': ctx.auc_amt,
            'yest_pct': ctx.yest_pct, 'boards': ctx.boards, 'circ_mv': ctx.circ_mv,
            'tag': ctx.pool_tag, 'sector_info': ctx.industry, 'last_amt': ctx.last_amt,
            'is_holding': ctx.is_holding, 'is_focus': ctx.is_focus
        }


# ================= 🚀 主程序入口 =================
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


def main():
    print(f"\n{Back.BLUE}{Fore.WHITE} F佬 · 盘中实时监控系统 (架构重构版 v8.0) {Style.RESET_ALL}")
    print("=" * 145)

    history_map, pool_map = load_tushare_pool_and_history()
    manual_focus = load_manual_focus()
    holdings = load_holdings()

    live_df = get_live_data()
    if live_df.empty: return

    # --- 提取当日一字板概念 ---
    print(f"{Fore.CYAN}⚙️ [3/4] 正在扫描全市场一字板，提取领涨板块基因...{Style.RESET_ALL}")
    limit_up_concepts = set()
    for _, row in live_df.iterrows():
        auc_pct_raw = row.get('竞价涨幅', row.get('涨幅', row.get('open_pct', 0)))
        if parse_pct(auc_pct_raw) > 9.8:
            info = history_map.get(clean_code(row.get('代码', row.get('code', ''))), {})
            for c in re.split(r'[/+,-]', info.get('industry', '')):
                if c.strip() and c.strip() != '未知': limit_up_concepts.add(c.strip())
    print(f"   └── 共捕捉到 {Fore.RED}{len(limit_up_concepts)}{Style.RESET_ALL} 个涨停强势概念")

    # --- 流水线引擎启动 ---
    print(f"{Fore.CYAN}⚙️ [4/4] 引擎点火: 正在执行流水线式除杂降噪与多维战法评估...{Style.RESET_ALL}")
    engine = AuctionScreenerEngine()
    results = []
    seen_codes = set()
    filter_stats = {}

    for _, row in live_df.iterrows():
        try:
            code = clean_code(row.get('代码', row.get('code', '')))
            if not code or code in seen_codes: continue
            seen_codes.add(code)

            is_holding = code in holdings
            is_focus = code in manual_focus or str(row.get('名称', '')) in manual_focus
            is_in_pool = code in pool_map

            if not (is_holding or is_focus or is_in_pool):
                filter_stats["不在监控池"] = filter_stats.get("不在监控池", 0) + 1
                continue

            # 组装上下文
            auc_pct_raw = row.get('竞价涨幅', row.get('涨幅', row.get('open_pct', 0)))
            info = history_map.get(code, {})

            ctx = LiveStockContext(
                code=code,
                name=row.get('name', ''),
                open_pct=parse_pct(auc_pct_raw),
                real_pct=parse_pct(row.get('涨幅', row.get('pct', 0))),
                auc_amt=parse_chinese_money(row.get('竞价金额', row.get('auc_amt', 0))),
                yest_pct=info.get('yest_pct', 0.0) if info.get('yest_pct', 0.0) != 0 else parse_pct(
                    row.get('昨日涨跌幅', 0)),
                last_amt=info.get('yest_amt', 0.0) if info.get('yest_amt', 0.0) > 0 else parse_chinese_money(
                    row.get('昨日成交额', 0)),
                circ_mv=info.get('circ_mv', 0.0) if info.get('circ_mv', 0.0) > 0 else parse_chinese_money(
                    row.get('流通市值', 0)),
                boards=info.get('boards', 0) if info.get('boards', 0) > 0 else (
                    int(str(row.get('连续涨停天数', '0')).strip()) if str(
                        row.get('连续涨停天数', '0')).strip().isdigit() else 0),
                industry=info.get('industry', '未知'),
                pool_tag=pool_map.get(code, ""),
                is_holding=is_holding,
                is_focus=is_focus,
                limit_up_concepts=limit_up_concepts
            )

            # 投入引擎评估
            res = engine.evaluate(ctx)

            if 'fail_reason' in res:
                filter_stats[res['fail_reason']] = filter_stats.get(res['fail_reason'], 0) + 1
            else:
                results.append(res)

        except Exception as e:
            filter_stats[f"解析异常({e})"] = filter_stats.get(f"解析异常({e})", 0) + 1

    # 排序与打印
    results.sort(key=lambda x: (x['is_holding'], x['is_focus'], x['score'], x['auc']), reverse=True)

    print("\n" + "=" * 145)
    print(f"{Fore.YELLOW}🛡️ 拦截器流水线明细：{Style.RESET_ALL}")
    for reason, count in filter_stats.items():
        if count > 0: print(f"  - {reason}: 拦截了 {count} 只无效标的")

    print("=" * 145)
    print(f"📊 战法精锐池 | 扫描总数: {len(live_df)} | {Fore.GREEN}高度聚焦老龙破局、弱转强与持仓防雷{Style.RESET_ALL}")
    print(
        f"{'代码':<8} {'名称':<6} {'竞价%':>6} {'现幅%':>6} {'昨幅%':>6}   {'竞价额':<8} {'连板':<4} {'市值':<8} {'昨额':<8} {'所属行业'}  {'AI决策与流向标签'}")
    print("-" * 155)

    display_count = 0
    for item in results:
        # 非持仓、非关注的票，置信分必须 >= 85 才配显示
        if not item['is_holding'] and not item['is_focus'] and item['score'] < 85: continue
        display_count += 1

        c_open = Fore.RED if item['open_pct'] > 0 else (Fore.GREEN if item['open_pct'] < 0 else Fore.WHITE)
        c_real = Fore.RED if item['real_pct'] > 0 else (Fore.GREEN if item['real_pct'] < 0 else Fore.WHITE)
        c_yest = Fore.RED if item['yest_pct'] > 0 else (Fore.GREEN if item['yest_pct'] < 0 else Fore.WHITE)

        auc_str = f"{int(item['auc'])}万"
        yest_str = "未知" if item['last_amt'] == 0 else (
            f"{item['last_amt'] / 10000:.1f}亿" if item['last_amt'] > 10000 else f"{int(item['last_amt'])}万")
        boards_str = f"{Fore.RED}{item['boards']}板{Style.RESET_ALL}" if item['boards'] >= 2 else ""
        mv_str = "未知" if item['circ_mv'] == 0 else (
            f"{item['circ_mv'] / 10000.0:.1f}亿" if item['circ_mv'] > 10000 else f"{int(item['circ_mv'])}万")

        prefix_icon = f"{Back.RED}{Fore.WHITE} 💼持仓 {Style.RESET_ALL} " if item['is_holding'] else (
            f"{Back.YELLOW}{Fore.BLACK} ⭐关注 {Style.RESET_ALL} " if item['is_focus'] else "")

        print(
            f"{item['code']:<8} {item['name']:<6} {c_open}{item['open_pct']:>6.2f}{Style.RESET_ALL}  {c_real}{item['real_pct']:>6.2f}{Style.RESET_ALL}  {c_yest}{item['yest_pct']:>6.2f}{Style.RESET_ALL}   {Fore.YELLOW}{auc_str:<8}{Style.RESET_ALL} {boards_str:<5} {mv_str:<8} {yest_str:<8} {item['sector_info']:<12} {prefix_icon}{item['decision']}")

    if display_count == 0: print(f"{Fore.YELLOW}当前无符合极端条件的精锐标的，请空仓等待或只处理持仓。{Style.RESET_ALL}")
    print("=" * 145)
    print(f"💡 最终仅显示 {Fore.GREEN}{display_count}{Style.RESET_ALL} 只高价值标的，方便极速决策！")


if __name__ == "__main__":
    main()