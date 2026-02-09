# ==============================================================================
# 🦅 Tushare 数据抓取聚合 (src/data/tushare_source/fetcher.py)
# 功能：统一管理所有 Tushare API 请求，包括行情、指数、同花顺榜单
# ==============================================================================
import pandas as pd
import time
from colorama import Fore
from src.data.tushare_source.client import TushareClient

# 尝试导入本地加载器 (用于竞价数据)
try:
    from src.data.ths_local import THSLocalLoader
    from src.config.settings import Config
except ImportError:
    THSLocalLoader = None


class TushareFetcher:
    def __init__(self):
        # ✅ 使用新的客户端单例获取接口
        self.pro = TushareClient.get_pro()

    def fetch_daily_full(self, date_str):
        """
        [1/3] 获取全市场个股基础行情 (日线 + 每日指标 + 竞价 + 涨跌停)
        """
        if not self.pro: return []
        print(f"🦅 正在拉取 {date_str} 数据 (分步执行)...")

        try:
            # 1. 获取日线 (Price, PCT)
            print(f"   ├── [1/5] 获取基础行情...", end="", flush=True)
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str,
                                            fields='ts_code,turnover_rate,circ_mv,total_mv,volume_ratio')
            print(" ✅")

            # 2. 获取昨日数据 (用于计算竞价量比)
            print(f"   ├── [2/5] 获取昨日数据...", end="", flush=True)
            prev_date = self._get_prev_date(date_str)
            df_prev = pd.DataFrame()
            if prev_date:
                df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
            print(" ✅")

            # 3. 获取竞价数据 (Tushare + 本地双保险)
            print(f"   ├── [3/5] 获取集合竞价...", end="", flush=True)
            df_auction = self._fetch_auction_data(date_str)
            print(" ✅")

            # 4. 获取同花顺涨跌停 (权威)
            print(f"   ├── [4/5] 获取同花顺数据...", end="", flush=True)
            ths_stats, df_ths_zt = self.fetch_ths_limit_stats(date_str)
            print(" ✅")

            # 5. 合并与清洗
            print(f"   └── [5/5] 数据合并...", end="", flush=True)

            # 合并流程
            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')
            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')

            # 标记涨停/炸板
            zt_codes = set(df_ths_zt['ts_code']) if not df_ths_zt.empty else set()

            # 转换 list[dict]
            result_pool = []

            # 预加载名称
            name_map = self._get_stock_names()

            for _, row in df_merge.iterrows():
                full_code = row['ts_code']

                # 竞价逻辑
                vol_auc = float(row.get('auc_vol', 0))  # 注意单位，假设本地已处理
                vol_last = float(row.get('last_vol', 0)) * 100  # Tushare vol单位是手
                auc_ratio = (vol_auc / vol_last) if vol_last > 0 else 0

                limit_days = 0
                is_zt = full_code in zt_codes
                # 如果在同花顺表里，尝试解析连板高度
                if is_zt and not df_ths_zt.empty:
                    # 简单匹配一下
                    matches = df_ths_zt[df_ths_zt['ts_code'] == full_code]
                    if not matches.empty:
                        status = str(matches.iloc[0].get('status', ''))
                        if '连板' in status:
                            limit_days = int(''.join(filter(str.isdigit, status)) or 1)
                        else:
                            limit_days = 1

                result_pool.append({
                    'code': full_code.split('.')[0],
                    'sina_code': full_code.lower().replace('.', ''),
                    'name': name_map.get(full_code, '未知'),
                    'price': row['close'],
                    'open_pct': (row['open'] - row['pre_close']) / row['pre_close'] * 100,
                    'today_pct': row['pct_chg'],
                    'turnover': row['turnover_rate'],
                    'amount': row['amount'] * 1000,
                    'vol_ratio': row.get('volume_ratio', 0),
                    'auction_ratio': auc_ratio,
                    'limit_days': limit_days,
                    'is_zt': is_zt,
                    'ts_code': full_code
                })

            print(" ✅")
            return result_pool

        except Exception as e:
            print(f" {Fore.RED}❌ 异常: {e}{Fore.RESET}")
            return []

    def fetch_market_index(self, date_str):
        """[2/3] 获取大盘指数"""
        if not self.pro: return {}
        print(f"   📊 正在获取大盘指数...", end="")
        targets = {'sh': '000001.SH', 'sz': '399001.SZ', 'gz': '399303.SZ'}
        result = {}
        try:
            for k, c in targets.items():
                df = self.pro.index_daily(ts_code=c, trade_date=date_str)
                if not df.empty:
                    result[k] = {
                        'pct': float(df.iloc[0]['pct_chg']),
                        'amount': float(df.iloc[0]['amount']) * 1000
                    }
            print(" ✅")
            return result
        except:
            print(f" {Fore.RED}❌{Fore.RESET}")
            return {}

    def fetch_ths_limit_stats(self, date_str):
        """[3/3] 获取同花顺涨跌停 (权威)"""
        if not self.pro: return {}, pd.DataFrame()
        # 这里复用之前的 ths_loader 逻辑
        try:
            df_up = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池')
            df_down = self.pro.limit_list_ths(trade_date=date_str, limit_type='跌停池')

            count_up = len(df_up) if not df_up.empty else 0
            count_down = len(df_down) if not df_down.empty else 0

            height = 0
            if count_up > 0 and 'status' in df_up.columns:
                # 简化的连板计算
                def p(s): return int(''.join(filter(str.isdigit, str(s))) or 1) if '连板' in str(s) else 1

                height = df_up['status'].apply(p).max()

            print(f"   🔥 权威校准: 涨停 {count_up} 家 | 跌停 {count_down} 家 | 最高板 {height}")
            return {'limit_up_count': count_up, 'limit_down_count': count_down, 'highest_plate': height}, df_up
        except:
            return {}, pd.DataFrame()

    def _get_prev_date(self, date_str):
        """辅助：获取上个交易日"""
        try:
            df = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)  # 取最近2个
            dates = df['cal_date'].tolist()
            if len(dates) == 2 and dates[1] == date_str:
                return dates[0]
            return None
        except:
            return None

    def _fetch_auction_data(self, date_str):
        """辅助：竞价数据 (优先本地文件)"""
        df_auc = pd.DataFrame()

        # 1. 尝试本地
        if THSLocalLoader:
            try:
                local_dir = getattr(Config, 'CALL_AUCTION_DIR', 'data/input/call_auction')
                loader = THSLocalLoader(local_dir)
                df_local = loader.load_auction_table(date_str)
                if not df_local.empty:
                    # 转换列名匹配 Tushare
                    # 本地: ts_code, auc_amt, auc_pct -> 需要 auc_vol 用于量比?
                    # 通常本地文件只有金额，量比计算比较麻烦，这里简化：
                    # 如果有本地金额，就信本地金额。量的部分尝试用 Tushare 补
                    df_auc = df_local[['ts_code', 'auc_amt']]
                    # 注意：本地数据通常没有 vol，只有 amt。
                    # 如果非常依赖量比，可能需要反算 price，这里先简化
                    return df_auc
            except:
                pass

        # 2. 尝试 Tushare
        try:
            df_auc = self.pro.stk_auction_o(trade_date=date_str, fields='ts_code,vol,amount')
            df_auc.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
            # Tushare vol 是手，转股 * 100
            df_auc['auc_vol'] = df_auc['auc_vol'] * 100
        except:
            pass

        return df_auc

    def _get_stock_names(self):
        """辅助：获取名称映射"""
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            return df.set_index('ts_code')['name'].to_dict()
        except:
            return {}