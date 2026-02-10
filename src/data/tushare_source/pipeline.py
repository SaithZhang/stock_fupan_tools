# src/data/tushare_source/pipeline.py
import pandas as pd
from colorama import Fore
from src.core.domain import Stock
from src.data.tushare_source.client import TushareClient

# 引入步骤插件 (假设您已按上一轮建议建立了 steps 目录)
from src.data.tushare_source.steps.basic import BasicInfoStep
from src.data.tushare_source.steps.auction import AuctionStep
from src.data.tushare_source.steps.limit import LimitBoardStep
from src.data.tushare_source.steps.sentiment import SentimentStep
from src.data.tushare_source.steps.money import SmartMoneyStep
from src.data.tushare_source.steps.chips import ChipStep


class StockDataPipeline:
    """
    🏭 [流水线引擎] 专门负责生产 Stock 对象列表
    符合开闭原则：新增个股数据源，只需在 self.steps 添加一步，不用改核心逻辑。
    """

    def __init__(self):
        self.pro = TushareClient.get_pro()
        # 在这里配置流水线工序
        self.steps = [
            BasicInfoStep(self.pro),
            AuctionStep(self.pro),
            LimitBoardStep(self.pro),
            SentimentStep(self.pro),
            SmartMoneyStep(self.pro),
            ChipStep(self.pro)
        ]

    def run(self, date_str) -> list[Stock]:
        if not self.pro: return []
        print(f"🦅 [流水线] 启动个股数据处理 ({date_str})...")

        ctx = {}  # 共享上下文

        # 1. 依次执行采集 (Fetch)
        for step in self.steps:
            step.fetch(date_str, ctx)

        if 'main_df' not in ctx or ctx['main_df'].empty:
            print(f" {Fore.RED}❌ 基础行情缺失，流水线终止{Fore.RESET}")
            return []

        # 2. 数据表自动对齐 (Merge)
        df_merge = ctx['main_df']
        for key, val in ctx.items():
            if key.endswith('_df') and key != 'main_df' and isinstance(val, pd.DataFrame) and not val.empty:
                df_merge = pd.merge(df_merge, val, on='ts_code', how='left')

        # 3. 对象构建与增强 (Enrich)
        stock_list = []
        name_map = self._get_name_map()

        print(f"   └── 对象封装与标签注入...", end="", flush=True)
        try:
            for _, row in df_merge.iterrows():
                # --- 基础对象构建 ---
                s = self._build_base_stock(row, name_map)

                # --- 执行增强步骤 ---
                for step in self.steps:
                    step.enrich(s, row, ctx)

                stock_list.append(s)
            print(" ✅")
            return stock_list

        except Exception as e:
            print(f"\n {Fore.RED}❌ 流水线异常: {e}{Fore.RESET}")
            return []

    def _build_base_stock(self, row, name_map):
        """构建纯净的 Stock 对象"""
        full_code = row['ts_code']
        # 预计算涨幅等基础字段
        calc_open_pct = 0.0
        if row['pre_close'] > 0:
            calc_open_pct = (row['open'] - row['pre_close']) / row['pre_close'] * 100

        # 竞价逻辑
        auc_pct = float(row.get('auc_pct') or 0)
        final_auc_pct = auc_pct if pd.notna(row.get('auc_pct')) else calc_open_pct

        vol_last = float(row.get('last_vol') or 0) * 100
        vol_auc = float(row.get('auc_vol') or 0) * 100
        auc_ratio = (vol_auc / vol_last) if vol_last > 0 else 0.0

        return Stock(
            code=full_code.split('.')[0],
            name=name_map.get(full_code, '未知'),
            ts_code=full_code,
            price=float(row['close']),
            open_price=float(row['open']),
            pct=float(row['pct_chg']),
            open_pct=calc_open_pct,
            amount=float(row['amount']) * 1000 if row.get('amount') else 0.0,
            turnover=float(row.get('turnover_rate') or 0),
            vol_ratio=float(row.get('volume_ratio') or 0),
            auc_amt=float(row.get('auc_amt') or 0),
            auc_pct=float(final_auc_pct or 0),
            auc_ratio=auc_ratio,
            call_auction_ratio=auc_ratio * 100,
            # 默认值
            is_zt=False, limit_days=0, is_st='ST' in name_map.get(full_code, ''), is_broken=False
        )

    def _get_name_map(self):
        try:
            return self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,name').set_index('ts_code')[
                'name'].to_dict()
        except:
            return {}