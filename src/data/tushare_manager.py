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
from src.data.ths_local import THSLocalLoader
from src.config.settings import Config

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
        """
        获取每日全市场数据快照 (终极版)
        特性:
        1. 分步进度显示，避免盲等
        2. 支持 Tushare 接口与本地同花顺文件(THSLocalLoader)双模驱动
        3. 自动计算竞价涨幅(优先本地，兜底使用开盘涨幅)
        """
        if not self.pro: return []
        if not date_str: date_str = self.get_trading_date()

        # 引入本地加载器 (延迟导入避免循环依赖)
        try:
            from src.data.ths_local import THSLocalLoader
            from src.config.settings import Config
        except ImportError:
            THSLocalLoader = None

        prev_date = self.get_prev_trade_date(date_str)
        print(f"{Fore.CYAN}🦅 正在拉取 {date_str} 数据 (分步执行)...")

        try:
            # --- A. 基础数据 ---
            print(f"   ├── [1/5] 获取基础行情 (Daily+Basic)...", end="", flush=True)
            df_daily = self.pro.daily(trade_date=date_str)
            df_basic = self.pro.daily_basic(trade_date=date_str, fields='ts_code,turnover_rate,volume_ratio,circ_mv,pe')
            print(f" ✅")

            # --- B. 昨日数据 ---
            print(f"   ├── [2/5] 获取昨日数据 (用于比对)...", end="", flush=True)
            df_prev = pd.DataFrame()
            if prev_date:
                try:
                    df_prev = self.pro.daily(trade_date=prev_date, fields='ts_code,vol')
                    df_prev.rename(columns={'vol': 'last_vol'}, inplace=True)
                except:
                    pass
            print(f" ✅")

            # --- C. 集合竞价数据 (Tushare + 本地同花顺文件双保险) ---
            print(f"   ├── [3/5] 获取集合竞价 (Auction)...", end="", flush=True)
            df_auction = pd.DataFrame()

            # 1. 尝试 Tushare 接口
            try:
                df_auction = self.pro.stk_auction_o(trade_date=date_str, fields='ts_code,vol,amount')
                df_auction.rename(columns={'vol': 'auc_vol', 'amount': 'auc_amt'}, inplace=True)
            except Exception:
                pass

            # 2. 如果 Tushare 没数据，尝试加载本地同花顺文件
            if df_auction.empty and THSLocalLoader:
                try:
                    # 尝试读取本地文件 (需在 settings.py 配置 CALL_AUCTION_DIR)
                    local_dir = getattr(Config, 'CALL_AUCTION_DIR', 'data/input/call_auction')
                    local_loader = THSLocalLoader(local_dir)
                    df_local = local_loader.load_auction_table(date_str)

                    if not df_local.empty:
                        # 转换字段以匹配 Tushare 格式
                        # 本地解析含: ts_code, auc_amt, auc_pct
                        df_auction = df_local[['ts_code', 'auc_amt', 'auc_pct']]
                        print(f" ✅ (本地:{len(df_auction)}条)", end="")
                    else:
                        print(f" ⚠️ (TS接口空 & 本地无文件)", end="")
                except Exception as e:
                    print(f" ❌ (本地读取误:{e})", end="")
            else:
                count = len(df_auction)
                msg = f" ✅ (TS接口:{count}条)" if count > 0 else " ⚠️ (0条)"
                print(msg, end="")

            print("")  # 换行

            # --- D. 同花顺数据 ---
            print(f"   ├── [4/5] 获取同花顺涨停/炸板...", end="", flush=True)
            df_ths_zt, df_ths_zb = self.fetch_ths_limit_data(date_str)

            # 兜底
            if df_ths_zt.empty:
                try:
                    limit_step = self.pro.limit_step(trade_date=date_str)
                    if not limit_step.empty:
                        limit_step['ths_desc'] = ''
                        limit_step.rename(columns={'nums': 'limit_days'}, inplace=True)
                        df_ths_zt = limit_step
                except:
                    pass
            print(f" ✅")

            # --- E. 数据合并 ---
            print(f"   └── [5/5] 数据清洗与合并...", end="", flush=True)

            # 1. 合并基础
            df_merge = pd.merge(df_daily, df_basic, on='ts_code', how='left')

            # 2. 合并昨日
            if not df_prev.empty:
                df_merge = pd.merge(df_merge, df_prev, on='ts_code', how='left')
            else:
                df_merge['last_vol'] = 0

            # 3. 合并竞价
            if not df_auction.empty:
                df_merge = pd.merge(df_merge, df_auction, on='ts_code', how='left')
            else:
                df_merge['auc_vol'] = 0
                df_merge['auc_amt'] = 0
                df_merge['auc_pct'] = 0.0  # 初始化该列

            # 4. 合并涨停
            if not df_ths_zt.empty:
                df_merge = pd.merge(df_merge, df_ths_zt, on='ts_code', how='left')
            else:
                df_merge['status'] = ''
                df_merge['tag'] = ''
                df_merge['lu_desc'] = ''

            zb_codes = set(df_ths_zb['ts_code'].tolist()) if not df_ths_zb.empty else set()

            # --- F. 逐行清洗与计算 ---
            result_pool = []
            for _, row in df_merge.iterrows():
                full_code = row['ts_code']
                pure_code = full_code.split('.')[0]
                market = full_code.split('.')[1].lower()
                sina_code = f"{market}{pure_code}"

                pct = float(row['pct_chg'])
                price = float(row['close'])

                # --- 计算开盘涨幅 (作为竞价涨幅的兜底) ---
                # 逻辑: (Open - PreClose) / PreClose
                calc_open_pct = 0.0
                if row['pre_close'] > 0:
                    calc_open_pct = (row['open'] - row['pre_close']) / row['pre_close'] * 100

                # --- 竞价数据逻辑 ---
                vol_today_auc = float(row.get('auc_vol', 0)) / 100
                vol_yest_full = float(row.get('last_vol', 0))
                auction_ratio = vol_today_auc / vol_yest_full if vol_yest_full > 0 else 0.0

                # 竞价涨幅: 优先用本地文件的 'auc_pct'，否则用计算出的 'calc_open_pct'
                local_auc_pct = float(row.get('auc_pct', 0.0)) if pd.notnull(row.get('auc_pct')) else 0.0
                final_auc_pct = local_auc_pct if local_auc_pct != 0.0 else calc_open_pct

                # --- 连板解析 ---
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
                    'open_pct': calc_open_pct,  # 原始开盘涨幅
                    'today_pct': pct,
                    'turnover': float(row['turnover_rate']) if pd.notnull(row['turnover_rate']) else 0,
                    'amount': float(row['amount']) * 1000,
                    'vol': float(row['vol']) * 100,
                    'vol_ratio': float(row['volume_ratio']) if pd.notnull(row['volume_ratio']) else 0,

                    # === 竞价核心字段 ===
                    'auc_amt': float(row.get('auc_amt', 0)),
                    'auction_ratio': auction_ratio,
                    'auc_pct': final_auc_pct,  # ✅ 最终使用的竞价涨幅
                    # ==================

                    'limit_days': limit_days,
                    'is_zt': is_zt,
                    'ts_code': full_code,
                    'ths_desc': str(row.get('lu_desc', '')).replace('nan', ''),
                    'is_broken': full_code in zb_codes
                }
                result_pool.append(item)

            # 补全名称
            self._enrich_names(result_pool)
            print(f" ✅ 完成")

            return result_pool

        except Exception as e:
            print(f"\n{Fore.RED}❌ 数据拉取异常: {e}")
            import traceback
            traceback.print_exc()
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