# ==============================================================================
# 📌 数据源层 (src/core/pool_data_source.py)
# 作用: 负责所有文件读取、清洗、格式转换。为核心逻辑提供纯净的数据对象。
# ==============================================================================
import pandas as pd
import os
import glob
import re
import sys
from datetime import datetime
from colorama import Fore

# ================= 🔧 必须加上这段路径修复代码 🔧 =================
# 获取当前脚本所在目录 (src/core)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (src/core -> src -> pyproject)
project_root = os.path.dirname(os.path.dirname(current_dir))
# 将根目录加入 Python 搜索路径，这样才能识别 'src.config'
if project_root not in sys.path:
    sys.path.append(project_root)

# 引入配置常量 (请确保 src/config/pool_config.py 存在)
from src.config.pool_config import (
    PROJECT_ROOT, INPUT_AK_DIR, INPUT_THS_DIR, OUTPUT_DIR, ARCHIVE_DIR,
    RISK_DIR, LHB_DIR, DAPAN_DIR,
    HOLDINGS_PATH, F_LAO_PATH, MANUAL_FOCUS_PATH
)

# 引入复用的外部模块 (保持现有依赖)
from src.core.data_loader import load_yesterday_ths_data
from src.core.market_data import MarketDataManager
from src.strategies.f_lao_model import load_ths_history


class PoolDataSource:
    """
    统一数据加载类。
    使用方法:
    loader = PoolDataSource()
    data = loader.get_base_market_data()
    lists = loader.load_text_lists()
    """

    def __init__(self):
        pass

    def get_base_market_data(self):
        """
        加载主数据：以 Akshare 数据为主，融合 THS 的竞价金额。
        返回: List[Dict] (清洗后的纯净数据)
        """
        # 1. 加载 Akshare 主表
        files = glob.glob(os.path.join(INPUT_AK_DIR, 'market_data_*.csv'))
        if not files:
            print(f"{Fore.RED}❌ [Data] 未找到 Akshare 数据文件! 请先运行 fetch_akshare.py")
            return []

        files.sort(reverse=True)
        latest_ak_file = files[0]
        print(f"{Fore.CYAN}📥 [Data] 加载主数据: {os.path.basename(latest_ak_file)}")

        try:
            df_ak = pd.read_csv(latest_ak_file, dtype={'code': str, 'limit_days': int})
        except Exception as e:
            print(f"{Fore.RED}❌ [Data] 读取 Akshare CSV 失败: {e}")
            return []

        # 2. 加载 THS 竞价数据 (辅助)
        auction_map = self._load_ths_auction_map()

        # 3. 数据融合与清洗
        clean_data = []
        for _, row in df_ak.iterrows():
            code = str(row['code']).zfill(6)

            # 基础价格字段清洗
            try:
                price = float(row['price'])
                prev_close = float(row['昨收'])
                open_price = float(row['今开'])
                high = float(row['最高'])
                low = float(row['最低'])
                pct = float(row['pct_chg'])

                # 计算各种涨幅
                open_pct = (open_price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                max_pct = (high - prev_close) / prev_close * 100 if prev_close > 0 else 0
                min_pct = (low - prev_close) / prev_close * 100 if prev_close > 0 else 0
            except:
                pct = 0;
                open_pct = 0;
                max_pct = 0;
                min_pct = 0;
                price = 0

            # 涨停状态判定
            limit_days = int(row.get('limit_days', 0))
            is_zt = limit_days > 0
            # 补漏逻辑：Akshare 说没板，但涨幅>9.8%，视为首板
            if not is_zt and pct > 9.8:
                is_zt = True
                limit_days = 1

            item = {
                'code': code,
                'name': str(row['name']),
                'today_pct': pct,
                'amount': float(row['amount']),
                'turnover': float(row.get('turnover_rate', 0)),
                'circ_mv': float(row.get('circ_mv', 0)),
                'vol_ratio': float(row.get('vol_ratio', 0)),
                'price': price,

                # 状态字段
                'limit_days': limit_days,
                'is_zt': is_zt,
                'zt_reason': str(row.get('reason', '')),
                'open_num': 0,  # Akshare 暂无此字段
                'is_first_limit': (limit_days == 1),

                # 价格衍生字段
                'open_pct': open_pct,
                'max_pct': max_pct,
                'min_pct': min_pct,

                # 外部融合数据
                'call_auction_amount': auction_map.get(code, 0),

                # 占位符 (防止 KeyError)
                'vol': 0,
                'vol_prev': 0,
                'pct_10': 0
            }
            clean_data.append(item)

        return clean_data

    def _load_ths_auction_map(self):
        """(内部方法) 读取 THS Table 文件解析竞价金额"""
        ths_files = glob.glob(os.path.join(INPUT_THS_DIR, 'Table-*.txt'))
        auction_map = {}

        if not ths_files:
            return {}

        ths_files.sort(reverse=True)
        latest_ths = ths_files[0]
        # print(f"{Fore.BLUE}📥 [Data] 加载辅助数据 (竞价): {os.path.basename(latest_ths)}")

        try:
            df_ths = None
            # 尝试多种编码
            for enc in ['gbk', 'utf-8', 'utf-16', 'gb18030']:
                try:
                    df_ths = pd.read_csv(latest_ths, sep=r'\t+', engine='python', encoding=enc, dtype=str)
                    if '代码' in df_ths.columns or '名称' in df_ths.columns:
                        break
                except:
                    continue

            if df_ths is not None:
                df_ths.columns = [c.strip() for c in df_ths.columns]
                col_code = next((c for c in df_ths.columns if '代码' in c), None)
                col_bid = next((c for c in df_ths.columns if '早盘竞价金额' in c), None)

                if col_code and col_bid:
                    for _, row in df_ths.iterrows():
                        c = re.sub(r'\D', '', str(row[col_code])).zfill(6)
                        val = row[col_bid]
                        # 解析 '1.2亿', '3000万'
                        if pd.isna(val) or val == '--':
                            amt = 0.0
                        else:
                            s = str(val).replace('亿', '*100000000').replace('万', '*10000')
                            try:
                                amt = eval(s)
                            except:
                                amt = 0.0
                        auction_map[c] = amt
        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ [Data] THS竞价数据解析异常: {e}")

        return auction_map

    def load_text_lists(self):
        """
        加载持仓、F佬、手动关注三个列表
        返回: (holdings_list, flao_map, manual_list)
        """

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

        holdings = _load_file(HOLDINGS_PATH, is_map=False)  # 持仓只需要 code list
        flao = _load_file(F_LAO_PATH, is_map=True)  # F佬需要备注
        manual = _load_file(MANUAL_FOCUS_PATH, is_map=False)

        # 将 manual 转为 set 方便后续查找 (包含代码和可能的名称, 这里简化为 code set，
        # 实际逻辑中如果 manual 包含名称，可以在这里扩展，但 PoolTagger 里一般用 code 匹配)
        # 这里为了兼容原逻辑，manual 我们返回一个简单的 list 或 set
        return set(holdings), flao, set(manual)

    def load_yesterday_broken_pool(self):
        """
        加载昨日策略池，寻找【炸板】股，用于今日反包策略
        """
        if not os.path.exists(OUTPUT_DIR): return {}

        # 找昨天及以前的文件
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

        print(f"{Fore.MAGENTA}🔙 [Data] 加载昨日炸板池: {target}")
        res = {}
        try:
            df = pd.read_csv(path, dtype=str)
            for _, row in df.iterrows():
                # 只要标签里有 '炸板'，就纳入观察
                if '炸板' in str(row.get('tag', '')):
                    res[row['code'].zfill(6)] = {
                        'amount': float(row.get('amount', 0)),
                        'tag': str(row.get('tag', ''))
                    }
        except:
            pass
        return res

    def load_lhb_data(self):
        """
        加载龙虎榜和著名席位
        返回: (codes_set, seat_map)
        """
        lhb_file = os.path.join(LHB_DIR, 'lhb_latest.csv')
        seat_file = os.path.join(LHB_DIR, 'lhb_famous_latest.csv')

        codes = set()
        seats = {}

        # 1. 榜单代码
        if os.path.exists(lhb_file):
            try:
                df = pd.read_csv(lhb_file, dtype=str)
                if '代码' in df.columns:
                    codes = set(df['代码'].apply(lambda x: str(x).zfill(6)).tolist())
            except:
                pass

        # 2. 席位详情
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
        """加载最新的风险/异动监管数据"""
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

                # 提取百分比数值
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
        """加载历史数据 (F佬模型用)"""
        # 复用已有的 logic，这里只是做个 wrapper
        return load_ths_history(INPUT_THS_DIR, days=days)

    def load_yesterday_full(self):
        """加载昨日全量数据 (计算 Ratio 用)"""
        return load_yesterday_ths_data()

    def load_market_sentiment(self):
        """加载大盘情绪 (MarketDataManager)"""
        md = MarketDataManager(DAPAN_DIR)
        loaded = md.load_data()
        return md, loaded