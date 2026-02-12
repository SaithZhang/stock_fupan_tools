# src/data/exporter.py

import pandas as pd
import os
from datetime import datetime
from colorama import Fore
from src.config.settings import Config


class ResultExporter:
    @staticmethod
    def export_pool(pool_data):
        """
        导出策略池到 CSV (保留所有字段，但优先展示核心列)
        """
        if not pool_data:
            print(f"{Fore.YELLOW}⚠️ 结果池为空，跳过导出。")
            return

        df = pd.DataFrame(pool_data)

        # 0. 按成交额排序 (如果有)
        if 'amount' in df.columns:
            df.sort_values(by='amount', ascending=False, inplace=True)

        # ✅ 1. 定义优先展示的列（按你希望的顺序）
        # 这些列会被强制排在表格的最左边，方便复盘
        priority_cols = [
            'sina_code',
            'name',
            'tag',               # 策略标签
            'price',
            'today_pct',
            'limit_up_type',     # 涨停类型 (首板/连板)
            'limit_days',        # 连板高度
            'risk_level',        # 风险等级

            # --- 🔥 核心资金数据 (重点) ---
            'amount',            # 总成交额
            'mf_lg_amount',      # 主力大单净流入 (万元)
            'mf_net_amount',     # 资金净流入 (万元)
            'mf_d5_amount',      # 5日主力净额 (万元)

            # --- 🔥 题材与热点 ---
            'ths_hot_concept',   # 同花顺热点概念

            # --- 核心技术指标 ---
            'turnover',          # 换手率
            'call_auction_ratio',# 竞价占比
            'winner_rate',       # 获利盘比例
            'cost_5pct',         # 底部支撑线
            'cost_95pct',        # 顶部压力线
        ]

        # ✅ 2. 智能重排列顺序
        # 逻辑：[优先列] + [原来有但没在优先表里的剩余列]
        # 这样既保证了重点在前，又保证了“一列都不虽然少”

        # 2.1 筛选出 df 里实际存在的优先列
        exist_priority_cols = [c for c in priority_cols if c in df.columns]

        # 2.2 找出剩下的列 (比如 code, ts_code, is_zt 等旧字段)
        remaining_cols = [c for c in df.columns if c not in exist_priority_cols]

        # 2.3 拼接最终顺序
        final_cols = exist_priority_cols + remaining_cols

        # 2.4 重组 DataFrame
        final_df = df[final_cols]

        # --- 导出文件 ---
        date_str = datetime.now().strftime("%Y%m%d")

        # 确保输出目录存在
        if not os.path.exists(Config.OUTPUT_DIR):
            os.makedirs(Config.OUTPUT_DIR, exist_ok=True)

        path_dated = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_v2_{date_str}.csv')
        path_latest = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')

        try:
            # encoding='utf-8-sig' 解决 Excel 打开乱码问题
            final_df.to_csv(path_dated, index=False, encoding='utf-8-sig')
            final_df.to_csv(path_latest, index=False, encoding='utf-8-sig')

            print(f"\n{Fore.GREEN}🎉 复盘完成！生成标的: {len(pool_data)} 只")
            print(f"📄 [历史] 竞价文件: {path_dated}")
            print(f"📄 [最新] 监控文件: {path_latest}")
            print(f"📊 列数统计: {len(final_cols)} 列 (重点列已前置)")

        except Exception as e:
            print(f"{Fore.RED}❌ 文件导出失败 (请检查文件是否被打开): {e}")