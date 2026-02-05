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
        df.sort_values(by='amount', ascending=False, inplace=True)

        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'risk_level', 'limit_up_type',
                'limit_days']
        for c in cols:
            if c not in df.columns: df[c] = ""

        date_str = datetime.now().strftime("%Y%m%d")

        # 路径处理
        path_dated = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_v2_{date_str}.csv')
        path_latest = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')

        try:
            df.to_csv(path_dated, index=False, encoding='utf-8-sig')
            df.to_csv(path_latest, index=False, encoding='utf-8-sig')

            print(f"\n{Fore.GREEN}🎉 复盘完成！生成标的: {len(pool_data)} 只")
            print(f"📄 [历史] 竞价文件: {path_dated}")
            print(f"📄 [最新] 监控文件: {path_latest}")
        except Exception as e:
            print(f"{Fore.RED}❌ 文件导出失败 (请检查文件是否被打开): {e}")