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
        导出策略池到 CSV
        """
        if not pool_data:
            print(f"{Fore.YELLOW}⚠️ 结果池为空，跳过导出。")
            return

        df = pd.DataFrame(pool_data)

        # 按成交额排序
        if 'amount' in df.columns:
            df.sort_values(by='amount', ascending=False, inplace=True)

        # ✅ 1. 定义想要导出的列（按你希望在表格里看到的顺序排列）
        # 建议把 [资金流向] 放在 [成交额] 旁边，方便对比
        ordered_cols = [
            'sina_code',
            'name',
            'tag',  # 策略标签
            'price',
            'today_pct',
            'limit_up_type',  # 涨停类型
            'risk_level',  # 风险等级

            # --- 核心资金数据 ---
            'amount',  # 总成交额
            'mf_lg_amount',  # 🔥 主力大单净流入 (新增)
            'mf_net_amount',  # 资金净流入 (新增)
            'mf_d5_amount',  # 5日主力净额 (新增)

            # --- 其他重要数据 ---
            'ths_hot_concept',  # 🔥 同花顺热点 (新增)
            'turnover',  # 换手率
            'limit_days',  # 连板数
            'call_auction_ratio'  # 竞价占比
        ]

        # ✅ 2. 补全缺失列（防止某些字段没获取到时报错）
        for c in ordered_cols:
            if c not in df.columns:
                df[c] = ""  # 缺失填空

        # ✅ 3. 强制重排每列的顺序 (只保留我们在 ordered_cols 里定义的列，或者保留所有但把核心列放前面)
        # 这里使用 reindex，只导出我们关心的列，保持表格清爽
        # 如果你还想保留 extra 里的其他杂项，可以使用: df = df[ordered_cols + [c for c in df.columns if c not in ordered_cols]]

        # 简单模式：只导出定义好的列，整齐划一
        final_df = df.reindex(columns=ordered_cols)

        date_str = datetime.now().strftime("%Y%m%d")

        # 路径处理
        path_dated = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_v2_{date_str}.csv')
        path_latest = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')

        try:
            # encoding='utf-8-sig' 是为了解决 Excel 打开乱码问题
            final_df.to_csv(path_dated, index=False, encoding='utf-8-sig')
            final_df.to_csv(path_latest, index=False, encoding='utf-8-sig')

            print(f"\n{Fore.GREEN}🎉 复盘完成！生成标的: {len(pool_data)} 只")
            print(f"📄 [历史] 竞价文件: {path_dated}")
            print(f"📄 [最新] 监控文件: {path_latest}")

        except Exception as e:
            print(f"{Fore.RED}❌ 文件导出失败 (请检查文件是否被打开): {e}")