# ==============================================================================
# 🦅 Tushare 数据驱动 (src/data/tushare_manager.py)
# Version: v2.5 (THS Ultimate)
# ==============================================================================

import tushare as ts
import pandas as pd
import re
from colorama import Fore
from typing import List, Dict, Tuple


class TushareManager:
    _instance = None
    TOKEN = "e90040a46bc696bd7c69380ab1c13973bb28eb031d013cf00936b97a323f"
    CUSTOM_URL = "http://lianghua.nanyangqiankun.top"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TushareManager, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        try:
            self.pro = ts.pro_api(self.TOKEN)
            self.pro._DataApi__token = self.TOKEN
            self.pro._DataApi__http_url = self.CUSTOM_URL
        except Exception as e:
            print(f"{Fore.RED}❌ Tushare 初始化失败: {e}")
            self.pro = None

    def get_trading_date(self) -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y%m%d')

    def fetch_ths_limit_data(self, date_str: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        获取同花顺数据的核心方法
        返回: (涨停池DF, 炸板池DF)
        """
        zt_df = pd.DataFrame()
        zb_df = pd.DataFrame()

        try:
            # 1. 抓取涨停池
            # 字段: ts_code, tag(首板/2连板), status(N连板), lu_desc(原因)
            zt_df = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池',
                                            fields='ts_code,tag,status,lu_desc,limit_type')
            if not zt_df.empty:
                print(f"{Fore.GREEN}   🔥 获取同花顺【涨停池】成功: {len(zt_df)} 条")

            # 2. 抓取炸板池 (用于做反包/弱转强)
            zb_df = self.pro.limit_list_ths(trade_date=date_str, limit_type='炸板池',
                                            fields='ts_code,lu_desc')
            if not zb_df.empty:
                print(f"{Fore.YELLOW}   💣 获取同花顺【炸板池】成功: {len(zb_df)} 条")

        except Exception as e:
            print(f"{Fore.RED}   ⚠️ 同花顺接口调用失败 (可能积分不足或无权限): {e}")
            print(f"   ℹ️ 将自动降级到普通 limit_step 接口")

        return zt_df, zb_df

    def _parse_limit_days(self, status_str, tag_str):
        """解析 '3连板', '4天2板', '首板' 为数字"""
        status_str = str(status_str)
        tag_str = str(tag_str)

        # 优先看 tag (如 "4天2板") -> 取 2
        # 或者 status (如 "3连板") -> 取 3

        # 1. 处理 "N连板"
        match = re.search(r'(\d+)连板', status_str)
        if match: return int(match.group(1))

        # 2. 处理 "首板"
        if '首板' in status_str or '首板' in tag_str: return 1

        # 3. 处理 "N天M板" -> 取 M
        match = re.search(r'\d+天(\d+)板', tag_str)
        if match: return int(match.group(1))

        # 4. 处理 "T字板", "一字板", "换手板" -> 如果没带数字，通常算 1 或 N
        # 这里比较模糊，如果前面没匹配到，默认为 1
        return 1

    def get_prev_trade_date(self, date_str: str) -> str:
        """
        获取指定日期的上一个交易日 (修复版)
        逻辑：向前多取一些日子，强制按日期排序，取小于 date_str 的最大日期
        """
        try:
            # 向前取 60 天，确保覆盖长假
            start_date = (pd.to_datetime(date_str) - pd.Timedelta(days=60)).strftime('%Y%m%d')

            # 获取日历，只取开盘日
            df = self.pro.trade_cal(exchange='', is_open='1',
                                    start_date=start_date, end_date=date_str,
                                    fields='cal_date')

            if df.empty: return ''

            # 强制排序
            df = df.sort_values(by='cal_date', ascending=True)
            dates = df['cal_date'].tolist()

            # 如果当前日期 date_str 在列表里，取它的前一个
            if date_str in dates:
                idx = dates.index(date_str)
                if idx > 0:
                    return dates[idx - 1]
            else:
                # 如果 date_str 不在列表里（比如今天是周六），取列表最后一个
                return dates[-1]

        except Exception as e:
            print(f"{Fore.RED}   ⚠️ 获取昨日日期失败: {e}")
            pass
        return ''

    def fetch_daily_snapshot(self, date_str: str = None) -> List[Dict]:
        if not self.pro: return []
        if not date_str: date_str = self.get_trading_date()

        # 1. 获取上一个交易日 (用于获取昨日成交量作为分母)
        prev_date = self.get_prev_trade_date(date_str)
        print(f"{Fore.CYAN}🦅 正在拉取 {date_str} 数据 (对比昨日: {prev_date})...")

        try:
            # --- A. 基础数据 (今日) ---
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str, fields='ts_code,turnover_rate,volume_ratio,circ_mv,pe')

            # --- B. 昨日数据 (只取 vol 改名为 last_vol) ---
            df_prev = pd.DataFrame()
            if prev_date:
                try:
                    df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                    df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
                except:
                    print(f"{Fore.YELLOW}   ⚠️ 获取昨日数据失败，竞价量比将无法计算")

            # --- C. 集合竞价数据 (今日 9:30) ---
            df_auction = pd.DataFrame()
            try:
                # 限量：单次最大10000，全市场约5000只，通常一次够用
                df_auction = self.pro.stk_auction_o(trade_date=date_str, fields='ts_code,vol,amount')
                df_auction.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
                if not df_auction.empty:
                    print(f"{Fore.GREEN}   🔔 获取【集合竞价】成功: {len(df_auction)} 条")
            except Exception as e:
                print(f"{Fore.RED}   ⚠️ 集合竞价接口失败 (需分钟权限): {e}")

            # --- D. 同花顺数据 ---
            df_ths_zt, df_ths_zb = self.fetch_ths_limit_data(date_str)

            # (limit_step 兜底逻辑)
            if df_ths_zt.empty:
                try:
                    limit_step = self.pro.limit_step(trade_date=date_str)
                    if not limit_step.empty:
                        limit_step['ths_desc'] = ''
                        limit_step.rename(columns={'nums': 'limit_days'}, inplace=True)
                        df_ths_zt = limit_step
                except:
                    pass

            # --- E. 数据合并 ---
            # 1. 合并今日基础
            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')

            # 2. 合并昨日成交量
            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            # 3. 合并竞价数据
            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')
            else:
                df_merge['auc_vol'] = 0
                df_merge['auc_amt'] = 0

            # 4. 合并涨停数据
            if not df_ths_zt.empty:
                df_merge = pd.merge(df_merge, df_ths_zt, on='ts_code', how='left')
            else:
                df_merge['status'] = '';
                df_merge['tag'] = '';
                df_merge['lu_desc'] = ''

            zb_codes = set(df_ths_zb['ts_code'].tolist()) if not df_ths_zb.empty else set()

            # --- F. 清洗与计算 ---
            result_pool = []
            for _, row in df_merge.iterrows():
                full_code = row['ts_code']
                pure_code = full_code.split('.')[0]
                market = full_code.split('.')[1].lower()
                sina_code = f"{market}{pure_code}"

                pct = float(row['pct_chg'])
                price = float(row['close'])

                # --- 核心计算：竞价爆量比 ---
                # 逻辑：今日竞价量 / 昨日全天量
                # Tushare 竞价接口单位为股，Daily单位为手，需统一为手
                vol_today_auc = float(row.get('auc_vol', 0)) / 100
                vol_yest_full = float(row.get('last_vol', 0))

                auction_ratio = 0.0
                if vol_yest_full > 0:
                    auction_ratio = vol_today_auc / vol_yest_full

                # 解析连板数
                limit_days = 0
                ths_desc = str(row.get('lu_desc', ''))
                ths_status = str(row.get('status', ''))
                ths_tag = str(row.get('tag', ''))

                is_zt = False
                in_zt_list = pd.notnull(row.get('status')) and row.get('status') != ''
                is_hard_zt = (pct > 9.5) and (row['high'] == price)

                if in_zt_list:
                    is_zt = True
                    limit_days = self._parse_limit_days(ths_status, ths_tag)
                elif is_hard_zt:
                    is_zt = True
                    limit_days = 1

                if ths_desc == 'nan': ths_desc = ""

                item = {
                    'code': pure_code,
                    'sina_code': sina_code,
                    'name': '',  # 后续 enrich 补充
                    'price': price,
                    'open_pct': (row['open'] - row['pre_close']) / row['pre_close'] * 100,
                    'today_pct': pct,
                    'turnover': float(row['turnover_rate']) if pd.notnull(row['turnover_rate']) else 0,
                    'amount': float(row['amount']) * 1000,
                    'vol': float(row['vol']) * 100,
                    'vol_ratio': float(row['volume_ratio']) if pd.notnull(row['volume_ratio']) else 0,

                    # === 新增竞价字段 ===
                    'auc_amt': float(row.get('auc_amt', 0)),  # 竞价金额
                    'auction_ratio': auction_ratio,  # 竞价量比 (0.05 = 5%)
                    # ==================

                    'limit_days': limit_days,
                    'is_zt': is_zt,
                    'ts_code': full_code,
                    'ths_desc': ths_desc,
                    'is_broken': full_code in zb_codes
                }
                result_pool.append(item)

            self._enrich_names(result_pool)
            return result_pool

        except Exception as e:
            print(f"{Fore.RED}❌ 数据拉取异常: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _enrich_names(self, pool: List[Dict]):
        try:
            df_stocks = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            name_map = df_stocks.set_index('ts_code')['name'].to_dict()
            for item in pool:
                item['name'] = name_map.get(item['ts_code'], '未知')
        except:
            pass

    def fetch_lhb_data(self, date_str: str = None) -> pd.DataFrame:
        if not date_str: date_str = self.get_trading_date()
        try:
            return self.pro.top_list(trade_date=date_str)
        except:
            return pd.DataFrame()