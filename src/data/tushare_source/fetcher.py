# ==============================================================================
# 🦅 Tushare 数据抓取聚合 (src/data/tushare_source/fetcher.py)
# Version: 3.1 (Returns Domain Objects)
# ==============================================================================
import pandas as pd
import time
from colorama import Fore
from src.data.tushare_source.client import TushareClient
from src.core.domain import Stock  # ✅ 引入新模型

try:
    from src.data.ths_local import THSLocalLoader
    from src.config.settings import Config
except ImportError:
    THSLocalLoader = None


class TushareFetcher:
    def __init__(self):
        self.pro = TushareClient.get_pro()

    def fetch_daily_full(self, date_str) -> list[Stock]:
        """
        [1/3] 获取全市场数据并封装为 Stock 对象
        """
        if not self.pro: return []
        print(f"🦅 正在拉取 {date_str} 数据 (分步执行)...")

        try:
            # 1. 获取日线
            print(f"   ├── [1/5] 获取基础行情...", end="", flush=True)
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str,
                                            fields='ts_code,turnover_rate,circ_mv,total_mv,volume_ratio')
            print(" ✅")

            # 2. 获取昨日数据
            print(f"   ├── [2/5] 获取昨日数据...", end="", flush=True)
            prev_date = self._get_prev_date(date_str)
            df_prev = pd.DataFrame()
            if prev_date:
                df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
            print(" ✅")

            # 3. 获取竞价
            print(f"   ├── [3/5] 获取集合竞价...", end="", flush=True)
            df_auction = self._fetch_auction_data(date_str)
            print(" ✅")

            # 4. 获取同花顺
            print(f"   ├── [4/5] 获取同花顺数据...", end="", flush=True)
            ths_stats, df_ths_zt = self.fetch_ths_limit_stats(date_str)
            print(" ✅")

            # 5. 合并与对象化
            print(f"   └── [5/5] 数据合并与对象化...", end="", flush=True)

            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')
            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')

            # 预处理集合
            zt_codes = set(df_ths_zt['ts_code']) if not df_ths_zt.empty else set()
            zb_codes = set()  # 如果你有炸板数据，也可以在这里处理

            name_map = self._get_stock_names()
            stock_list = []

            for _, row in df_merge.iterrows():
                full_code = row['ts_code']

                # --- 计算逻辑 ---
                # 1. 开盘涨幅
                calc_open_pct = 0.0
                if row['pre_close'] > 0:
                    calc_open_pct = (row['open'] - row['pre_close']) / row['pre_close'] * 100

                # 2. 竞价逻辑
                vol_auc = float(row.get('auc_vol', 0))  # 注意：如果是本地数据，这里可能为0
                vol_last = float(row.get('last_vol', 0)) * 100  # 手 -> 股

                # 优先使用本地文件里的 auc_pct，否则用开盘涨幅兜底
                # 这里的 auc_pct 来源于 _fetch_auction_data 处理后的列
                auc_pct = float(row.get('auc_pct', 0)) if pd.notnull(row.get('auc_pct')) and row.get(
                    'auc_pct') != 0 else calc_open_pct

                # 简单的竞价量比计算 (如果没有本地auc_vol，这里会是0，不影响)
                auc_ratio = (vol_auc / vol_last) if vol_last > 0 else 0.0

                # 3. 连板解析
                limit_days = 0
                ths_status = ""
                ths_desc = ""

                if full_code in zt_codes and not df_ths_zt.empty:
                    matches = df_ths_zt[df_ths_zt['ts_code'] == full_code]
                    if not matches.empty:
                        item = matches.iloc[0]
                        ths_status = str(item.get('status', ''))
                        ths_desc = str(item.get('lu_desc', ''))
                        if '连板' in ths_status:
                            limit_days = int(''.join(filter(str.isdigit, ths_status)) or 1)
                        else:
                            limit_days = 1

                # --- ✅ 实例化 Stock 对象 ---
                s = Stock(
                    code=full_code.split('.')[0],
                    name=name_map.get(full_code, '未知'),
                    ts_code=full_code,
                    price=float(row['close']),
                    open_price=float(row['open']),
                    pct=float(row['pct_chg']),
                    open_pct=calc_open_pct,
                    amount=float(row['amount']) * 1000,
                    turnover=float(row.get('turnover_rate', 0)),
                    vol_ratio=float(row.get('volume_ratio', 0)),

                    # 竞价
                    auc_amt=float(row.get('auc_amt', 0)),
                    auc_pct=auc_pct,
                    auc_ratio=auc_ratio,
                    call_auction_ratio=auc_ratio * 100,  # 兼容

                    # 状态
                    is_zt=(full_code in zt_codes),
                    limit_days=limit_days,
                    ths_status=ths_status,
                    ths_desc=ths_desc,
                    is_broken=(full_code in zb_codes)
                )

                stock_list.append(s)

            print(" ✅")
            return stock_list

        except Exception as e:
            print(f" {Fore.RED}❌ 异常: {e}{Fore.RESET}")
            import traceback
            traceback.print_exc()
            return []

    # ... (Fetch Index, Fetch THS Stats, Helpers 保持不变，可以直接复制之前的逻辑) ...
    # 为了完整性，这里补充剩下的方法

    def fetch_market_index(self, date_str):
        if not self.pro: return {}
        print(f"   📊 正在获取大盘指数...", end="")
        targets = {'sh': '000001.SH', 'sz': '399001.SZ', 'gz': '399303.SZ'}
        result = {}
        try:
            for k, c in targets.items():
                df = self.pro.index_daily(ts_code=c, trade_date=date_str)
                if not df.empty:
                    result[k] = {'pct': float(df.iloc[0]['pct_chg']), 'amount': float(df.iloc[0]['amount']) * 1000}
            print(" ✅")
            return result
        except:
            print(" ❌")
            return {}

    def fetch_ths_limit_stats(self, date_str):
        if not self.pro: return {}, pd.DataFrame()
        try:
            df_up = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池')
            df_down = self.pro.limit_list_ths(trade_date=date_str, limit_type='跌停池')

            count_up = len(df_up) if not df_up.empty else 0
            count_down = len(df_down) if not df_down.empty else 0

            height = 0
            if count_up > 0 and 'status' in df_up.columns:
                def p(s): return int(''.join(filter(str.isdigit, str(s))) or 1) if '连板' in str(s) else 1

                height = df_up['status'].apply(p).max()

            print(f"   🔥 权威校准: 涨停 {count_up} 家 | 跌停 {count_down} 家 | 最高板 {height}")
            return {'limit_up_count': count_up, 'limit_down_count': count_down, 'highest_plate': height}, df_up
        except:
            return {}, pd.DataFrame()

    def _get_prev_date(self, date_str):
        try:
            df = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)
            dates = df['cal_date'].tolist()
            if len(dates) == 2 and dates[1] == date_str: return dates[0]
            return None
        except:
            return None

    def _fetch_auction_data(self, date_str):
        df_auc = pd.DataFrame()
        # 1. 本地
        if THSLocalLoader:
            try:
                local_dir = getattr(Config, 'CALL_AUCTION_DIR', 'data/input/call_auction')
                loader = THSLocalLoader(local_dir)
                df_local = loader.load_auction_table(date_str)
                if not df_local.empty:
                    return df_local[['ts_code', 'auc_amt', 'auc_pct']]
            except:
                pass
        # 2. Tushare
        try:
            df_auc = self.pro.stk_auction_o(trade_date=date_str, fields='ts_code,vol,amount')
            df_auc.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
            df_auc['auc_vol'] = df_auc['auc_vol'] * 100
        except:
            pass
        return df_auc

    def _get_stock_names(self):
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            return df.set_index('ts_code')['name'].to_dict()
        except:
            return {}