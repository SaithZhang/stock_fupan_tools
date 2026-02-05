# ==============================================================================
# 🦅 Tushare 数据驱动 (src/data/tushare_manager.py)
# Version: v2.6 (Modular Client Integration)
# ==============================================================================

import pandas as pd
import re
from colorama import Fore
from typing import List, Dict, Tuple
from datetime import datetime

# 👇 核心改动：引入我们刚封装好的客户端工厂
from src.utils.tushare_client import get_tushare_client


class TushareManager:
    _instance = None

    def __new__(cls):
        """单例模式：确保全局只初始化一次 API 连接"""
        if cls._instance is None:
            cls._instance = super(TushareManager, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        """初始化逻辑大大简化，不再硬编码 Token"""
        self.pro = get_tushare_client()
        if not self.pro:
            print(f"{Fore.RED}❌ TushareManager 初始化失败: 无法获取客户端实例")

    def get_trading_date(self) -> str:
        return datetime.now().strftime('%Y%m%d')

    def fetch_ths_limit_data(self, date_str: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        获取同花顺数据的核心方法
        返回: (涨停池DF, 炸板池DF)
        """
        zt_df = pd.DataFrame()
        zb_df = pd.DataFrame()

        if not self.pro: return zt_df, zb_df

        try:
            # 1. 抓取涨停池
            zt_df = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池',
                                            fields='ts_code,tag,status,lu_desc,limit_type')
            if not zt_df.empty:
                print(f"{Fore.GREEN}   🔥 获取同花顺【涨停池】成功: {len(zt_df)} 条")

            # 2. 抓取炸板池
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

        match = re.search(r'(\d+)连板', status_str)
        if match: return int(match.group(1))

        if '首板' in status_str or '首板' in tag_str: return 1

        match = re.search(r'\d+天(\d+)板', tag_str)
        if match: return int(match.group(1))

        return 1

    def get_prev_trade_date(self, date_str: str) -> str:
        """获取上一个交易日"""
        if not self.pro: return ''
        try:
            start_date = (pd.to_datetime(date_str) - pd.Timedelta(days=60)).strftime('%Y%m%d')
            df = self.pro.trade_cal(exchange='', is_open='1',
                                    start_date=start_date, end_date=date_str,
                                    fields='cal_date')
            if df.empty: return ''

            df = df.sort_values(by='cal_date', ascending=True)
            dates = df['cal_date'].tolist()

            if date_str in dates:
                idx = dates.index(date_str)
                if idx > 0: return dates[idx - 1]
            else:
                return dates[-1]

        except Exception as e:
            print(f"{Fore.RED}   ⚠️ 获取昨日日期失败: {e}")
            pass
        return ''

    def fetch_daily_snapshot(self, date_str: str = None) -> List[Dict]:
        """获取每日全市场数据快照 (含竞价、技术面基础)"""
        if not self.pro: return []
        if not date_str: date_str = self.get_trading_date()

        prev_date = self.get_prev_trade_date(date_str)
        print(f"{Fore.CYAN}🦅 正在拉取 {date_str} 数据 (对比昨日: {prev_date})...")

        try:
            # --- A. 基础数据 ---
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str, fields='ts_code,turnover_rate,volume_ratio,circ_mv,pe')

            # --- B. 昨日数据 ---
            df_prev = pd.DataFrame()
            if prev_date:
                try:
                    df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                    df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
                except:
                    print(f"{Fore.YELLOW}   ⚠️ 获取昨日数据失败，竞价量比将无法计算")

            # --- C. 集合竞价 ---
            df_auction = pd.DataFrame()
            try:
                df_auction = self.pro.stk_auction_o(trade_date=date_str, fields='ts_code,vol,amount')
                df_auction.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
                if not df_auction.empty:
                    print(f"{Fore.GREEN}   🔔 获取【集合竞价】成功: {len(df_auction)} 条")
            except Exception as e:
                print(f"{Fore.RED}   ⚠️ 集合竞价接口失败: {e}")

            # --- D. 同花顺数据 ---
            df_ths_zt, df_ths_zb = self.fetch_ths_limit_data(date_str)

            # 兜底降级
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
            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')

            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')
            else:
                df_merge['auc_vol'] = 0;
                df_merge['auc_amt'] = 0

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

                # 竞价量比计算
                vol_today_auc = float(row.get('auc_vol', 0)) / 100
                vol_yest_full = float(row.get('last_vol', 0))
                auction_ratio = vol_today_auc / vol_yest_full if vol_yest_full > 0 else 0.0

                # 连板与涨停判定
                limit_days = 0
                ths_status = str(row.get('status', ''))
                ths_tag = str(row.get('tag', ''))
                is_zt = False

                if pd.notnull(row.get('status')) and row.get('status') != '':
                    is_zt = True
                    limit_days = self._parse_limit_days(ths_status, ths_tag)
                elif (pct > 9.5) and (row['high'] == price):
                    is_zt = True
                    limit_days = 1

                item = {
                    'code': pure_code,
                    'sina_code': sina_code,
                    'name': '',
                    'price': price,
                    'open_pct': (row['open'] - row['pre_close']) / row['pre_close'] * 100,
                    'today_pct': pct,
                    'turnover': float(row['turnover_rate']) if pd.notnull(row['turnover_rate']) else 0,
                    'amount': float(row['amount']) * 1000,
                    'vol': float(row['vol']) * 100,
                    'vol_ratio': float(row['volume_ratio']) if pd.notnull(row['volume_ratio']) else 0,
                    'auc_amt': float(row.get('auc_amt', 0)),
                    'auction_ratio': auction_ratio,
                    'limit_days': limit_days,
                    'is_zt': is_zt,
                    'ts_code': full_code,
                    'ths_desc': str(row.get('lu_desc', '')).replace('nan', ''),
                    'is_broken': full_code in zb_codes
                }
                result_pool.append(item)

            self._enrich_names(result_pool)
            return result_pool

        except Exception as e:
            print(f"{Fore.RED}❌ 数据拉取异常: {e}")
            return []

    def _enrich_names(self, pool: List[Dict]):
        if not self.pro: return
        try:
            df_stocks = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
            name_map = df_stocks.set_index('ts_code')['name'].to_dict()
            for item in pool:
                item['name'] = name_map.get(item['ts_code'], '未知')
        except:
            pass

    def fetch_lhb_data(self, date_str: str = None) -> pd.DataFrame:
        if not self.pro: return pd.DataFrame()
        if not date_str: date_str = self.get_trading_date()
        try:
            return self.pro.top_list(trade_date=date_str)
        except:
            return pd.DataFrame()