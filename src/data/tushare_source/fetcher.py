# ==============================================================================
# 🦅 Tushare 数据抓取聚合 (src/data/tushare_source/fetcher.py)
# Version: 3.4 (Cloud Auction: Fully Automated)
# ==============================================================================
import pandas as pd
import time
import re
from colorama import Fore
from src.data.tushare_source.client import TushareClient
from src.core.domain import Stock


class TushareFetcher:
    def __init__(self):
        self.pro = TushareClient.get_pro()

    def fetch_daily_full(self, date_str) -> list[Stock]:
        if not self.pro: return []
        print(f"🦅 正在拉取 {date_str} 数据 (分步执行)...")

        try:
            # 1. 获取日线
            print(f"   ├── [1/4] 获取基础行情...", end="", flush=True)
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str,
                                            fields='ts_code,turnover_rate,circ_mv,total_mv,volume_ratio')
            print(" ✅")

            # 2. 获取昨日数据 (用于计算量比的分母)
            print(f"   ├── [2/4] 获取昨日数据...", end="", flush=True)
            prev_date = self._get_prev_date(date_str)
            df_prev = pd.DataFrame()
            if prev_date:
                df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
            print(" ✅")

            # 3. 获取云端竞价 (直接调用接口)
            print(f"   ├── [3/4] 获取云端竞价...", end="", flush=True)
            df_auction = self._fetch_cloud_auction(date_str)
            print(f" ✅ (获取 {len(df_auction)} 条)")

            # 4. 获取同花顺涨跌停 (权威)
            print(f"   ├── [4/4] 获取同花顺数据...", end="", flush=True)
            ths_stats, df_ths_zt = self.fetch_ths_limit_stats(date_str)
            print(" ✅")

            # [新增步骤] 5. 获取全市场筹码数据 (一次性拉取，极速)
            print(f"   ├── [5/6] 获取全市场筹码分布...", end="", flush=True)
            df_chips = self.fetch_cyq_perf_full(date_str)
            # 转为字典以便 O(1) 查找: { '000001.SZ': {'winner_rate': 90, ...} }
            chip_map = df_chips.set_index('ts_code').to_dict('index') if not df_chips.empty else {}
            print(f" ✅ (获取 {len(df_chips)} 条)")

            # 6. 合并与清洗 (原步骤5顺延)
            print(f"   └── [6/6] 数据合并与对象化...", end="", flush=True)

            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')
            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')

            zt_codes = set(df_ths_zt['ts_code']) if not df_ths_zt.empty else set()
            # 炸板数据暂略，如需可加
            zb_codes = set()

            name_map = self._get_stock_names()
            stock_list = []

            for _, row in df_merge.iterrows():
                full_code = row['ts_code']
                stock_name = name_map.get(full_code, '未知')

                # --- 1. 开盘涨幅 (基于日线 Open) ---
                calc_open_pct = 0.0
                if row['pre_close'] > 0:
                    calc_open_pct = (row['open'] - row['pre_close']) / row['pre_close'] * 100

                # --- 2. 竞价逻辑 (基于云端数据) ---
                # amount: Tushare单位是元
                # vol: Tushare单位是手，转成股 * 100
                auc_amt = float(row.get('auc_amt', 0))

                # 竞价涨幅：优先使用云端计算好的 auc_pct
                # 如果云端没数据 (NaN)，则降级使用开盘涨幅 calc_open_pct
                auc_pct_val = float(row.get('auc_pct', 0))
                if pd.isna(row.get('auc_pct')):
                    final_auc_pct = calc_open_pct
                else:
                    final_auc_pct = auc_pct_val

                # 竞价量比
                # last_vol 是昨日全天成交量(手) * 100 -> 股
                # auc_vol 是竞价成交量(手) * 100 -> 股
                vol_last = float(row.get('last_vol', 0)) * 100
                vol_auc = float(row.get('auc_vol', 0)) * 100

                auc_ratio = (vol_auc / vol_last) if vol_last > 0 else 0.0

                # --- 3. 连板解析 (Regex) ---
                limit_days = 0
                ths_status_str = ""
                limit_type_str = ""
                ths_desc = ""

                is_zt = full_code in zt_codes
                if is_zt and not df_ths_zt.empty:
                    matches = df_ths_zt[df_ths_zt['ts_code'] == full_code]
                    if not matches.empty:
                        item = matches.iloc[0]
                        ths_status_str = str(item.get('tag', ''))  # "4天4板"
                        limit_type_str = str(item.get('status', ''))  # "换手板"
                        ths_desc = str(item.get('lu_desc', ''))

                        # 解析高度
                        limit_days = 1
                        m = re.search(r'(\d+)(连板|板)', ths_status_str)
                        if m:
                            limit_days = int(m.group(1))
                        elif '首板' in ths_status_str:
                            limit_days = 1

                # --- 4. 统一识别 ST ---
                _is_st = 'ST' in stock_name.upper()

                # --- 实例化 ---
                s = Stock(
                    code=full_code.split('.')[0],
                    name=stock_name,
                    ts_code=full_code,

                    price=float(row['close']),
                    open_price=float(row['open']),
                    pct=float(row['pct_chg']),
                    open_pct=calc_open_pct,

                    # --- 建议的稳健代码块 (替换原有的实例化参数) ---
                    amount=float(row['amount']) * 1000 if row.get('amount') else 0.0,
                    turnover=float(row.get('turnover_rate') or 0),
                    vol_ratio=float(row.get('volume_ratio') or 0),

                    # 竞价数据
                    auc_amt=float(row.get('auc_amt') or 0),  # 同样建议加上保护
                    auc_pct=final_auc_pct,
                    auc_ratio=auc_ratio,
                    call_auction_ratio=auc_ratio * 100,

                    # 状态
                    is_zt=is_zt,
                    is_st=_is_st,
                    limit_days=limit_days,
                    ths_status=ths_status_str,
                    limit_type=limit_type_str,
                    ths_desc=ths_desc,
                    is_broken=(full_code in zb_codes)
                )
                # --- 💉 注入筹码数据 ---
                if full_code in chip_map:
                    data = chip_map[full_code]
                    s.winner_rate = float(data.get('winner_rate', 0))
                    s.cost_5pct = float(data.get('cost_5pct', 0))
                    s.cost_95pct = float(data.get('cost_95pct', 0))
                    s.weight_avg = float(data.get('weight_avg', 0))

                stock_list.append(s)

            print(" ✅")
            return stock_list

        except Exception as e:
            print(f" {Fore.RED}❌ 异常: {e}{Fore.RESET}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_market_index(self, date_str):
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
        if not self.pro: return {}, pd.DataFrame()
        try:
            fields = 'ts_code,name,trade_date,tag,status,lu_desc'
            df_up = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池', fields=fields)
            time.sleep(0.2)
            df_down = self.pro.limit_list_ths(trade_date=date_str, limit_type='跌停池', fields=fields)

            count_up = len(df_up) if not df_up.empty else 0
            count_down = len(df_down) if not df_down.empty else 0

            height = 0
            if count_up > 0 and 'tag' in df_up.columns:
                def parse_height(s):
                    s = str(s)
                    m = re.search(r'(\d+)(连板|板)', s)
                    if m: return int(m.group(1))
                    if '首板' in s: return 1
                    return 1

                height = df_up['tag'].apply(parse_height).max()

            print(f"   🔥 权威校准: 涨停 {count_up} 家 | 跌停 {count_down} 家 | 最高板 {height}")
            return {'limit_up_count': count_up, 'limit_down_count': count_down, 'highest_plate': height}, df_up
        except Exception as e:
            print(f"获取榜单失败: {e}")
            return {}, pd.DataFrame()

    def _get_prev_date(self, date_str):
        try:
            df = self.pro.trade_cal(exchange='', is_open='1', end_date=date_str, limit=2)
            dates = df['cal_date'].tolist()
            if len(dates) == 2 and dates[1] == date_str:
                return dates[0]
            return None
        except:
            return None

    def _fetch_cloud_auction(self, date_str):
        """
        🔥 核心：直接从 Tushare 云端获取竞价数据，并计算涨幅
        """
        try:
            # 1. 调用接口
            # 注意：amount单位是元，vol是手，price是元，pre_close是元
            df = self.pro.stk_auction(trade_date=date_str, fields='ts_code,vol,amount,price,pre_close')

            if df.empty:
                return pd.DataFrame()

            # 2. 数据清洗
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df['pre_close'] = pd.to_numeric(df['pre_close'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')  # 元
            df['vol'] = pd.to_numeric(df['vol'], errors='coerce')  # 手

            # 3. 计算竞价涨幅 (Price - PreClose) / PreClose
            # 避免除以0
            df['auc_pct'] = 0.0
            mask = df['pre_close'] > 0
            df.loc[mask, 'auc_pct'] = (df.loc[mask, 'price'] - df.loc[mask, 'pre_close']) / df.loc[
                mask, 'pre_close'] * 100

            # 4. 重命名以匹配后续逻辑
            # vol -> auc_vol, amount -> auc_amt
            df.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)

            # 返回这三列即可，merge的时候会自动匹配 ts_code
            return df[['ts_code', 'auc_vol', 'auc_amt', 'auc_pct']]

        except Exception as e:
            print(f" {Fore.RED}⚠️ 云端竞价拉取失败: {e}")
            return pd.DataFrame()

    def _get_stock_names(self):
        try:
            df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            return df.set_index('ts_code')['name'].to_dict()
        except:
            return {}

    def fetch_cyq_perf(self, ts_code=None, trade_date=None):
        """
        获取每日筹码平均成本和胜率 (cyq_perf)
        用途：识别筹码密集区间、计算当前获利盘比例
        """
        if not self.pro: return pd.DataFrame()
        try:
            # 接口文档：获取A股每日筹码平均成本和胜率情况
            df = self.pro.cyq_perf(ts_code=ts_code, trade_date=trade_date)
            return df
        except Exception as e:
            print(f" {Fore.RED}⚠️ 筹码胜率数据获取失败: {e}")
            return pd.DataFrame()

    def fetch_cyq_chips(self, ts_code, trade_date=None):
        """
        获取每日筹码分布情况 (cyq_chips)
        用途：绘制筹码分布图，寻找支撑位和压力位
        """
        if not self.pro: return pd.DataFrame()
        try:
            # 接口文档：获取各价位占比
            df = self.pro.cyq_chips(ts_code=ts_code, trade_date=trade_date)
            return df
        except Exception as e:
            print(f" {Fore.RED}⚠️ 筹码分布数据获取失败: {e}")
            return pd.DataFrame()

    def _integrate_chips_to_stock(self, stock_list, date_str):
        """
        (预留) 将筹码概况集成到 Stock 对象中
        注意：由于 cyq_perf 只能按 code 或 date 查，
        如果全市场扫描，建议按 trade_date 循环提取或分页提取。
        """
        # 如果积分足够（5000+），可以尝试单次获取全天
        df_perf = self.fetch_cyq_perf(trade_date=date_str)

        if not df_perf.empty:
            perf_map = df_perf.set_index('ts_code').to_dict('index')
            for s in stock_list:
                perf = perf_map.get(s.ts_code)
                if perf:
                    # 在 Stock 对象中动态添加筹码属性
                    s.winner_rate = float(perf.get('winner_rate', 0))
                    s.avg_cost = float(perf.get('weight_avg', 0))
                    s.cost_85pct = float(perf.get('cost_85pct', 0))  # 压力位参考
        return stock_list

    def fetch_cyq_perf_full(self, date_str):
        """
        获取指定日期全市场的筹码数据
        注意：cyq_perf 每日18:00更新，盘中跑可能拿不到当日数据（需拿昨日）
        """
        if not self.pro: return pd.DataFrame()
        try:
            # 不传 ts_code，只传 trade_date，即获取全市场
            df = self.pro.cyq_perf(trade_date=date_str)
            return df
        except Exception as e:
            print(f" {Fore.RED}⚠️ 筹码数据获取失败 (可能是权限或时间未到): {e}{Fore.RESET}")
            return pd.DataFrame()