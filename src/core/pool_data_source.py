# ==============================================================================
# 📌 数据源层 (src/core/pool_data_source.py)
# 作用: 负责所有文件读取、清洗、格式转换。
# 修改版: 支持融合 THS 的行业/竞价数据 + Akshare 的板块指数数据
# ==============================================================================
import pandas as pd
import os
import glob
import re
import sys
from datetime import datetime
from colorama import Fore

# ================= 🔧 路径修复 =================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 引入配置常量
from src.config.pool_config import (
    PROJECT_ROOT, INPUT_AK_DIR, INPUT_THS_DIR, OUTPUT_DIR, ARCHIVE_DIR,
    RISK_DIR, LHB_DIR, DAPAN_DIR,
    HOLDINGS_PATH, F_LAO_PATH, MANUAL_FOCUS_PATH
)

from src.core.data_loader import load_yesterday_ths_data
from src.core.market_data import MarketDataManager
from src.strategies.f_lao_model import load_ths_history


class PoolDataSource:
    def __init__(self):
        pass

    def get_base_market_data(self):
        """
        加载主数据：以 Akshare 为主，融合 THS 的竞价金额 + 行业归属。
        """
        # 1. 加载 Akshare 主表 (fetch_akshare 生成)
        files = glob.glob(os.path.join(INPUT_AK_DIR, 'market_data_*.csv'))
        if not files:
            print(f"{Fore.RED}❌ [Data] 未找到 Akshare 数据! 请先运行 fetch_akshare.py")
            return []

        files.sort(reverse=True)
        latest_ak_file = files[0]
        # 提取日期供后续加载板块数据使用
        self.current_date_str = re.findall(r'\d{8}', os.path.basename(latest_ak_file))[0]
        print(f"{Fore.CYAN}📥 [Data] 加载主数据: {os.path.basename(latest_ak_file)}")

        try:
            df_ak = pd.read_csv(latest_ak_file, dtype={'code': str, 'limit_days': int})
        except Exception as e:
            print(f"{Fore.RED}❌ [Data] 读取 Akshare CSV 失败: {e}")
            return []

        # 2. 加载 THS 辅助数据 (竞价 + 行业)
        # 返回: dict { code: { 'call_amount': float, 'industry': str, 'concept': str } }
        aux_map = self._load_ths_aux_data()

        # 3. 数据融合与清洗
        clean_data = []
        for _, row in df_ak.iterrows():
            code = str(row['code']).zfill(6)

            # --- 基础清洗 ---
            try:
                price = float(row['price'])
                prev_close = float(row['昨收'])
                open_price = float(row['今开'])
                high = float(row['最高'])
                low = float(row['最低'])
                pct = float(row['pct_chg'])

                open_pct = (open_price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                max_pct = (high - prev_close) / prev_close * 100 if prev_close > 0 else 0
                min_pct = (low - prev_close) / prev_close * 100 if prev_close > 0 else 0
            except:
                pct = 0;
                open_pct = 0;
                max_pct = 0;
                min_pct = 0;
                price = 0

            # --- 涨停判定 ---
            limit_days = int(row.get('limit_days', 0))
            is_zt = limit_days > 0
            if not is_zt and pct > 9.8:  # 补漏
                is_zt = True
                limit_days = 1

            # --- 获取辅助信息 ---
            aux_info = aux_map.get(code, {})

            item = {
                'code': code,
                'name': str(row['name']),
                'today_pct': pct,
                'amount': float(row['amount']),
                'turnover': float(row.get('turnover_rate', 0)),
                'circ_mv': float(row.get('circ_mv', 0)),
                'vol_ratio': float(row.get('vol_ratio', 0)),
                'price': price,

                # 状态
                'limit_days': limit_days,
                'is_zt': is_zt,
                'zt_reason': str(row.get('reason', '')),
                'open_num': 0,
                'is_first_limit': (limit_days == 1),

                # 价格衍生
                'open_pct': open_pct,
                'max_pct': max_pct,
                'min_pct': min_pct,

                # --- 融合 THS 数据 ---
                'call_auction_amount': aux_info.get('call_amount', 0),
                'bk_industry': aux_info.get('industry', ''),  # 融合行业
                'bk_concept': aux_info.get('concept', ''),  # 融合细分

                # 占位符
                'vol': 0, 'vol_prev': 0, 'pct_10': 0
            }
            clean_data.append(item)

        return clean_data

    def _load_ths_aux_data(self):
        """
        读取 THS 导出文件 (Table-xx.txt/csv)
        解析: 竞价金额, 所属行业, 细分行业
        """
        ths_files = glob.glob(os.path.join(INPUT_THS_DIR, 'Table-*.txt'))
        # 兼容 csv 后缀
        if not ths_files:
            ths_files = glob.glob(os.path.join(INPUT_THS_DIR, 'Table-*.csv'))

        aux_map = {}

        if not ths_files:
            print(f"{Fore.YELLOW}⚠️ [Data] 未找到 THS 导出文件 (无法获取竞价/行业信息)")
            return {}

        ths_files.sort(reverse=True)
        latest_ths = ths_files[0]

        try:
            df_ths = None
            # 尝试多种编码读取
            for enc in ['gbk', 'utf-8', 'utf-16', 'gb18030']:
                try:
                    df_ths = pd.read_csv(latest_ths, sep=None, engine='python', encoding=enc, dtype=str)
                    if '代码' in df_ths.columns or '名称' in df_ths.columns:
                        break
                except:
                    continue

            if df_ths is not None:
                df_ths.columns = [c.strip() for c in df_ths.columns]

                # 寻找关键列名
                col_code = next((c for c in df_ths.columns if '代码' in c), None)
                col_bid = next((c for c in df_ths.columns if '竞价金额' in c), None)
                col_ind = next((c for c in df_ths.columns if '所属行业' in c), None)
                col_con = next((c for c in df_ths.columns if '细分行业' in c), None)

                if col_code:
                    for _, row in df_ths.iterrows():
                        c = re.sub(r'\D', '', str(row[col_code])).zfill(6)

                        # 1. 解析竞价
                        amt = 0.0
                        if col_bid:
                            val = row[col_bid]
                            if not pd.isna(val) and val != '--':
                                s = str(val).replace('亿', '*100000000').replace('万', '*10000')
                                try:
                                    amt = eval(s)
                                except:
                                    amt = 0.0

                        # 2. 解析行业
                        ind = str(row[col_ind]) if col_ind and not pd.isna(row[col_ind]) else ''
                        con = str(row[col_con]) if col_con and not pd.isna(row[col_con]) else ''

                        aux_map[c] = {
                            'call_amount': amt,
                            'industry': ind,
                            'concept': con
                        }
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ [Data] THS辅助数据解析异常: {e}")

        return aux_map

    def load_sector_data(self):
        """
        加载 Akshare 下载的板块/指数数据 (fetch_akshare 产出)
        用于 Context 里的全局大盘判断
        """
        # 使用 get_base_market_data 解析出的日期，或者默认当天
        date_str = getattr(self, 'current_date_str', datetime.now().strftime("%Y%m%d"))

        def _read_ak_sector(sub_folder, prefix):
            # 寻找对应日期的文件
            path = os.path.join(INPUT_AK_DIR, sub_folder, f'{prefix}_chk_{date_str}.csv')
            if not os.path.exists(path):
                # 尝试找最近的一个
                files = glob.glob(os.path.join(INPUT_AK_DIR, sub_folder, f'{prefix}_chk_*.csv'))
                if files:
                    files.sort(reverse=True)
                    path = files[0]
                else:
                    return pd.DataFrame()
            try:
                return pd.read_csv(path)
            except:
                return pd.DataFrame()

        return {
            'indices': _read_ak_sector('indices', 'index'),
            'industries': _read_ak_sector('industries', 'industry'),
            'concepts': _read_ak_sector('concepts', 'concept')
        }

    # --- 以下保持原样 ---
    def load_text_lists(self):
        def _load_file(path, is_map=False):
            if not os.path.exists(path): return {} if is_map else []
            res = {} if is_map else []
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip() or line.startswith('#'): continue
                        parts = line.strip().split(maxsplit=1)
                        code = re.sub(r'\D', '', parts[0])
                        if len(code) == 6:
                            if is_map:
                                res[code] = parts[1] if len(parts) > 1 else "关注"
                            else:
                                res.append(code)
            except:
                pass
            return res

        holdings = _load_file(HOLDINGS_PATH, is_map=False)
        flao = _load_file(F_LAO_PATH, is_map=True)
        manual = _load_file(MANUAL_FOCUS_PATH, is_map=False)
        return set(holdings), flao, set(manual)

    def load_yesterday_broken_pool(self):
        if not os.path.exists(OUTPUT_DIR): return {}
        files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('strategy_pool_') and f.endswith('.csv')]
        if not files and os.path.exists(ARCHIVE_DIR):
            files = [f for f in os.listdir(ARCHIVE_DIR) if f.startswith('strategy_pool_') and f.endswith('.csv')]
        today_str = datetime.now().strftime("%Y%m%d")
        target = None
        files.sort(reverse=True)
        for f in files:
            d = re.findall(r'\d{8}', f)
            if d and d[0] < today_str:
                target = f
                break
        if not target: return {}
        path = os.path.join(OUTPUT_DIR, target)
        if not os.path.exists(path): path = os.path.join(ARCHIVE_DIR, target)
        res = {}
        try:
            df = pd.read_csv(path, dtype=str)
            for _, row in df.iterrows():
                if '炸板' in str(row.get('tag', '')):
                    res[row['code'].zfill(6)] = {
                        'amount': float(row.get('amount', 0)),
                        'tag': str(row.get('tag', ''))
                    }
        except:
            pass
        return res

    def load_lhb_data(self):
        lhb_file = os.path.join(LHB_DIR, 'lhb_latest.csv')
        seat_file = os.path.join(LHB_DIR, 'lhb_famous_latest.csv')
        codes = set()
        seats = {}
        if os.path.exists(lhb_file):
            try:
                df = pd.read_csv(lhb_file, dtype=str)
                if '代码' in df.columns:
                    codes = set(df['代码'].apply(lambda x: str(x).zfill(6)).tolist())
            except:
                pass
        if os.path.exists(seat_file):
            try:
                df = pd.read_csv(seat_file, dtype=str)
                for _, row in df.iterrows():
                    label = row['游资标签']

                    def _parse(val, prefix):
                        if pd.isna(val) or str(val) == 'nan': return
                        for p in str(val).split(' '):
                            p = p.strip()
                            if not p: continue
                            name = p.split('(')[0].split('/')[0]
                            note = p.split('(')[1].rstrip(')') if '(' in p else ""
                            final_p = prefix
                            if "锁仓" in note or "锁仓" in p:
                                final_p = "🔒"
                            elif "加仓" in note:
                                final_p = "➕"
                            if name not in seats: seats[name] = set()
                            seats[name].add(f"{final_p}{label}")

                    _parse(row.get('买入股票'), "💰")
                    _parse(row.get('卖出股票'), "🏃")
            except:
                pass
        return codes, seats

    def load_risk_data(self):
        if not os.path.exists(RISK_DIR): return {}
        files = [f for f in os.listdir(RISK_DIR) if f.startswith('risk_') and f.endswith('.csv')]
        if not files: return {}
        files.sort(reverse=True)
        target = os.path.join(RISK_DIR, files[0])
        print(f"{Fore.MAGENTA}🔎 [Data] 加载风险数据: {files[0]}")
        risk_map = {}
        try:
            df = pd.read_csv(target)
            for _, row in df.iterrows():
                name = str(row['股票名称']).strip()
                msg = str(row.get('当前累计偏离值', ''))
                match = re.search(r'(-?\d+\.?\d*)%', msg)
                val = float(match.group(1)) if match else 0.0
                rule = str(row.get('监管规则', ''))
                risk_map[name] = {
                    'risk_level': str(row.get('风险等级', '🟢 Safe')),
                    'risk_msg': msg,
                    'risk_rule': rule,
                    'trigger_next': str(row.get('异动触发条件', '')),
                    'deviation_val_10d': val if '10日' in rule else 0.0,
                    'deviation_val_30d': val if '30日' in rule else 0.0
                }
        except Exception as e:
            print(f"⚠️ [Data] 风险数据解析失败: {e}")
        return risk_map

    def load_history_data(self, days=5):
        return load_ths_history(INPUT_THS_DIR, days=days)

    def load_yesterday_full(self):
        return load_yesterday_ths_data()

    def load_market_sentiment(self):
        md = MarketDataManager(DAPAN_DIR)
        loaded = md.load_data()
        return md, loaded