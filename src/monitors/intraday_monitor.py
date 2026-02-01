# ==============================================================================
# 📌 F佬/Bo佬 盘中实时作战指挥室 - 【模块化重构版 v2.5】
# 核心升级：混合动力模式 (API实时行情 + 本地竞价数据融合)
# Last Modified: 2026-01-29
# ==============================================================================
import pandas as pd
import akshare as ak
import os
import sys
import time
import datetime
import glob
import re
import math
from colorama import init, Fore, Style, Back

if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

init(autoreset=True)

# ================= ⚙️ 0. 全局配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

try:
    from src.utils.data_loader import load_holdings, load_pool_full, load_manual_focus
except ImportError:
    print(f"{Fore.YELLOW}⚠️ 提示：独立运行模式{Style.RESET_ALL}")


    def load_holdings():
        return {}


    def load_pool_full():
        return {}


    def load_manual_focus():
        return {}


# ================= 🛠️ 1. 工具模块 =================
class Utils:
    @staticmethod
    def str_to_float(val):
        """强力转换数字"""
        if val is None: return 0.0
        if isinstance(val, (float, int)): return 0.0 if math.isnan(val) else float(val)
        val_str = str(val).strip().replace(',', '')
        if val_str in ['', '--', 'nan', 'None', 'NaN']: return 0.0
        if '%' in val_str: return float(val_str.replace('%', ''))

        mult = 1.0
        if '亿' in val_str:
            mult = 100000000.0
            val_str = val_str.replace('亿', '')
        elif '万' in val_str:
            mult = 10000.0
            val_str = val_str.replace('万', '')
        try:
            return float(val_str) * mult
        except:
            return 0.0

    @staticmethod
    def format_amount(num):
        if num is None or num == 0: return "0"
        try:
            num = float(num)
            if num > 100000000:
                return f"{num / 100000000:.2f}亿"
            elif num > 10000:
                return f"{num / 10000:.0f}万"
            else:
                return str(int(num))
        except:
            return str(num)

    @staticmethod
    def clean_stock_code(code_raw):
        code = str(code_raw).strip()
        digits = re.findall(r'\d+', code)
        return digits[0].zfill(6) if digits else code


# ================= 💾 2. 数据引擎 (核心升级) =================
class DataEngine:

    @staticmethod
    def load_local_file(file_path):
        """读取本地文件（支持UTF8/GBK自动识别）"""
        print(f"DEBUG: 正在读取文件 -> {file_path}")  # <--- 新增
        try:
            df = None
            encodings = ['utf-8', 'gbk', 'gb18030', 'utf-16']

            # 1. 尝试不同编码读取
            for enc in encodings:
                try:
                    # 尝试 tab 分隔 (同花顺默认)
                    df = pd.read_csv(file_path, sep='\t', encoding=enc, dtype=str)
                    if not df.empty and len(df.columns) > 1: break
                except:
                    pass

                try:
                    # 尝试自动分隔 (CSV)
                    df = pd.read_csv(file_path, sep=None, engine='python', encoding=enc, dtype=str)
                    if not df.empty and len(df.columns) > 1: break
                except:
                    pass

            if df is None and file_path.endswith(('.xlsx', '.xls')):
                try:
                    df = pd.read_excel(file_path, dtype=str)
                except:
                    pass

            if df is None or df.empty: return None

            # 在 df 读取成功后，列名清洗前，打印原始列名
            if df is not None:
                print(f"DEBUG: 原始列名 -> {df.columns.tolist()}")  # <--- 新增

            # 2. 列名清洗
            df.columns = [str(c).strip().replace('\n', '').replace('\r', '') for c in df.columns]

            # 3. 映射列名
            mapping = {
                '代码': ['代码', '证券代码'],
                '名称': ['名称', '证券名称'],
                '最新价': ['现价', '最新价', '收盘价'],
                '涨跌幅': ['涨幅', '涨幅%'],
                '成交额': ['成交额', '当日成交额', '总金额', '金额'],
                '成交量': ['成交量', '总手', '总量', 'vol'],
                '量比': ['量比'],
                '竞价成交额': ['早盘竞价金额', '竞价金额', '集合竞价', '开盘金额'],
                '竞价涨幅': ['竞价涨幅%', '开盘涨幅', '竞价涨幅'],
            }

            rename_dict = {}
            for std, aliases in mapping.items():
                for alias in aliases:
                    if alias in df.columns:
                        rename_dict[alias] = std
                        break
            df = df.rename(columns=rename_dict)
            print(f"DEBUG: 映射后列名 -> {df.columns.tolist()}")  # <--- 新增

            if '代码' not in df.columns: return None

            df['代码'] = df['代码'].apply(Utils.clean_stock_code)

            # 数值转换
            for col in ['竞价成交额', '竞价涨幅', '量比', '成交量', '成交额']:
                if col in df.columns:
                    df[col] = df[col].apply(Utils.str_to_float)

            return df
        except:
            return None

    @staticmethod
    def get_latest_local_file():
        """获取最新的本地文件"""
        intraday_dir = os.path.join(PROJECT_ROOT, "data", "input", "intraday")
        if not os.path.exists(intraday_dir): os.makedirs(intraday_dir)
        files = glob.glob(os.path.join(intraday_dir, "*.*"))
        valid_files = [f for f in files if f.endswith(('.txt', '.xls', '.xlsx', '.csv'))]
        if not valid_files: return None
        return max(valid_files, key=os.path.getmtime)

    @staticmethod
    def fetch_data_hybrid():
        """【混合模式】API实时行情 + 本地竞价数据融合"""

        # 1. 尝试读取本地文件 (不管API通不通，先读本地作为补充)
        local_df = None
        local_path = DataEngine.get_latest_local_file()
        local_info = ""

        if local_path:
            local_df = DataEngine.load_local_file(local_path)
            if local_df is not None:
                gap = time.time() - os.path.getmtime(local_path)
                delay_str = f"{gap / 60:.0f}分前" if gap > 60 else "刚刚"
                local_info = f"📂 本地({delay_str})"

        # 2. 获取 API 实时数据
        api_df = None
        source_name = ""

        # 优先东财
        try:
            api_df = ak.stock_zh_a_spot_em()
            if api_df is not None and not api_df.empty:
                source_name = "🌐 实时(东财)"
        except:
            pass

        # 备用新浪
        if api_df is None:
            try:
                api_df = ak.stock_zh_a_spot()
                if api_df is not None and not api_df.empty:
                    rename_map = {'symbol': '代码', 'name': '名称', 'trade': '最新价', 'changepercent': '涨跌幅',
                                  'volume': '成交量', 'amount': '成交额', 'open': '今开', 'high': '最高', 'low': '最低'}
                    api_df = api_df.rename(columns=rename_map)
                    api_df['代码'] = api_df['代码'].apply(lambda x: x[2:])
                    source_name = "🔄 备用(新浪)"
            except:
                pass

        # 3. 数据融合 (Merge Logic)
        final_df = None
        status_str = ""

        if api_df is not None:
            # 基础是API
            final_df = api_df
            status_str = source_name

            # 如果有本地文件，把本地的 竞价/量比/总手 补进去
            if local_df is not None:
                # 建立本地数据字典
                local_data = local_df.set_index('代码').to_dict('index')

                # 定义需要补全的列
                cols_to_merge = ['竞价成交额', '竞价涨幅', '量比', '成交量', '总手']

                for col in cols_to_merge:
                    if col not in final_df.columns:
                        final_df[col] = 0.0  # 先初始化

                # 遍历 API 数据，填补本地数据
                def fill_data(row):
                    code = row['代码']
                    if code in local_data:
                        src = local_data[code]
                        # 补全竞价
                        if row['竞价成交额'] == 0: row['竞价成交额'] = src.get('竞价成交额', 0)
                        if row['竞价涨幅'] == 0: row['竞价涨幅'] = src.get('竞价涨幅', 0)
                        # 补全量比 (新浪API通常没有量比)
                        if row.get('量比', 0) == 0: row['量比'] = src.get('量比', 0)
                        # 补全成交量 (如果API没返回)
                        if row.get('成交量', 0) == 0:
                            row['成交量'] = src.get('成交量', src.get('总手', 0))
                    return row

                final_df = final_df.apply(fill_data, axis=1)
                status_str += f" + {local_info}"

        elif local_df is not None:
            # API 挂了，完全用本地
            final_df = local_df
            status_str = f"{local_info} (纯离线模式)"

        else:
            return None, "❌ 无数据"

        # 4. 再次清洗数值，防止 nan
        num_cols = ['最新价', '涨跌幅', '竞价成交额', '竞价涨幅', '量比', '成交量', '成交额']
        for col in num_cols:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(Utils.str_to_float)

        return final_df, status_str


# ================= 🧠 3. 策略引擎 =================
class StrategyEngine:
    @staticmethod
    def analyze(row, holding_info, idx_pct):
        price = row.get('最新价', 0)
        pct = row.get('涨跌幅', 0)
        if price == 0: return (0, "", "", 0.0)

        # 核心：计算均价乖离
        vol = row.get('成交量', 0)
        amt = row.get('成交额', 0)

        vwap = price
        if vol > 0:
            avg_p = amt / vol
            # 单位修正 (手 vs 股)
            if avg_p > price * 10:
                vwap = amt / (vol * 100)
            else:
                vwap = avg_p

        bias = (price - vwap) / vwap * 100 if vwap > 0 else 0

        # 信号判定
        signals = []
        is_limit_up = (pct > 9.8 and price < 30) or (pct > 19.8)

        open_p = row.get('今开', price)
        vr = row.get('量比', 0)

        if is_limit_up: signals.append((10, "🚀涨停封板", Fore.MAGENTA))

        if holding_info:
            if bias > 4.0 and not is_limit_up: signals.append((8, "🚀急拉卖T", Fore.MAGENTA))
            if bias < -3.0: signals.append((8, "🌊急杀买T", Fore.CYAN))
        else:
            # 弱转强
            if open_p < vwap and price > vwap and pct > 3.0 and vr > 1.2:
                signals.append((6, "★弱转强", Fore.RED))
            # 人气
            if pct > 8.0 and not is_limit_up:
                signals.append((7, "🔥人气扫板", Fore.RED))

        if not signals: return (0, "观察", Fore.WHITE, bias)
        signals.sort(key=lambda x: x[0], reverse=True)
        return (signals[0][0], signals[0][1], signals[0][2], bias)


# ================= 🎨 4. 显示引擎 =================
class DisplayEngine:
    @staticmethod
    def print_dashboard(current_time, source_status, up_cnt, down_cnt):
        print(f"\n{Back.BLUE}{Fore.WHITE} {current_time} {Style.RESET_ALL} | 📡 {source_status}")
        print(f"🔥 市场情绪: 涨停 {up_cnt} 家 | 跌停 {down_cnt} 家")
        print("-" * 130)
        print(
            f"{'代码':<7} {'名称':<8} {'涨幅%':<8} {'现价':<8} {'乖离%':<7} {'量比':<6} {'竞价额':<9} {'竞价%':<7} {'信号':<12} {'核心标签'}")
        print("-" * 130)

    @staticmethod
    def print_row(item):
        c_pct = Fore.RED if item['pct'] > 0 else Fore.GREEN
        c_code = Back.YELLOW + Fore.BLACK if item['is_hold'] else (Back.BLUE + Fore.WHITE if item['is_manual'] else "")

        amt_str = Utils.format_amount(item['call_amt'])
        tag_disp = str(item['tag']).split('/')[0].replace('F佬', '').strip()[:15]

        print(
            f"{c_code}{item['code']}{Style.RESET_ALL:<0} "
            f"{item['name']:<8} "
            f"{c_pct}{item['pct']:>7.2f}{Style.RESET_ALL} "
            f"{item['price']:>7.2f} "
            f"{item['bias']:>7.1f} "
            f"{item['vr']:>6.1f} "
            f"{amt_str:<9} "
            f"{item['call_pct']:>7.2f} "
            f"{item['sig_color']}{item['sig_text']:<12}{Style.RESET_ALL} "
            f"{Fore.CYAN}{tag_disp}{Style.RESET_ALL}"
        )


# ================= 🎮 5. 主程序 =================
def main():
    print(f"\n{Back.RED}{Fore.WHITE} F佬 · 作战指挥室 (混合动力版 v2.5) {Style.RESET_ALL}")

    holdings = load_holdings()
    pool_map = load_pool_full()
    manual_map = load_manual_focus()
    monitor_codes = set(holdings) | set(pool_map.keys()) | set(manual_map.keys())

    # 获取数据 (自动融合 API + 本地)
    df, source_status = DataEngine.fetch_data_hybrid()

    if df is None:
        print(f"\n{Back.RED}{Fore.WHITE} ❌ 无数据来源！ {Style.RESET_ALL}")
        return

    # 统计
    up_cnt = len(df[df['涨跌幅'] > 9.8])
    down_cnt = len(df[df['涨跌幅'] < -9.8])

    # 筛选
    if len(df) > 1000:
        df_target = df[df['代码'].isin(monitor_codes)].copy()
        if df_target.empty:  # 兜底显示涨幅榜
            df_target = df.sort_values(by='涨跌幅', ascending=False).head(30)
    else:
        df_target = df.copy()

    display_list = []
    for _, row in df_target.iterrows():
        code = row['代码']
        holding_info = holdings.get(code)

        sig_level, sig_text, sig_color, bias = StrategyEngine.analyze(row, holding_info, 0)

        display_list.append({
            'code': code, 'name': row['名称'],
            'price': row['最新价'], 'pct': row['涨跌幅'],
            'bias': bias, 'sig_text': sig_text, 'sig_color': sig_color,
            'is_hold': holding_info is not None, 'is_manual': code in manual_map,
            'vr': row.get('量比', 0),
            'call_amt': row.get('竞价成交额', 0),
            'call_pct': row.get('竞价涨幅', 0),
            'tag': pool_map.get(code, {}).get('tag', '')
        })

    display_list.sort(key=lambda x: (not x['is_hold'], not x['is_manual'], -x['pct']))

    DisplayEngine.print_dashboard(datetime.datetime.now().strftime('%H:%M:%S'), source_status, up_cnt, down_cnt)
    for item in display_list:
        DisplayEngine.print_row(item)
    print("=" * 130 + "\n")


if __name__ == "__main__":
    main()