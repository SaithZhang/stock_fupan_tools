import pandas as pd
import time
import json
import os
from colorama import Fore
from src.data.tushare_source.steps.base import BaseDataStep


class ThsBoardStep(BaseDataStep):
    """
    [P7] 行业/概念全覆盖插件
    策略：
    1. 保底：获取全市场 5000+ 只股票的基础行业 (Tushare standard)
    2. 热点：获取同花顺 Top 领涨概念 (叠加高亮)
    3. 输出：生成全量映射表 json
    """

    def fetch(self, date_str: str, context: dict, step_idx=0, total_steps=0):
        # 动态打印步骤号
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[7/?]"
        print(f"   ├── {prefix} 行业与题材挖掘...", end="", flush=True)

        try:
            # === 1. 保底：获取全市场基础行业 (5000+ 覆盖) ===
            # fields='ts_code,industry'
            df_basic = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,industry')

            # 初始化大字典: { '000001': '银行' }
            full_map = {}
            if not df_basic.empty:
                for _, row in df_basic.iterrows():
                    code = row['ts_code'].split('.')[0]
                    # 默认只显示行业，如 "软件服务"
                    full_map[code] = str(row['industry']) if row['industry'] else "其他"

            # === 2. 增强：挖掘同花顺热门概念 (Top 8) ===
            hot_info_count = 0
            df_indices = self.pro.ths_index(exchange='A', type='N')  # N=概念

            if not df_indices.empty:
                # 拿前800个指数去查涨幅
                ts_codes = ",".join(df_indices['ts_code'].tolist()[:800])
                df_daily = self.pro.ths_daily(ts_code=ts_codes, trade_date=date_str, fields='ts_code,pct_change')

                if not df_daily.empty:
                    # 取涨幅前 8 的板块
                    top_boards = df_daily.sort_values(by='pct_change', ascending=False).head(8)

                    code_name_map = df_indices.set_index('ts_code')['name'].to_dict()

                    for _, row in top_boards.iterrows():
                        board_code = row['ts_code']
                        board_name = code_name_map.get(board_code, board_code)
                        if len(board_name) > 6: continue

                        # 拉成分股
                        df_members = self.pro.ths_member(ts_code=board_code)
                        time.sleep(0.3)

                        if not df_members.empty:
                            for stock_code in df_members['con_code']:
                                pure_code = stock_code.split('.')[0]

                                # 核心逻辑：如果已经在 map 里（肯定是有的），则在前面追加热门概念
                                # 格式变成: "🔥固态电池 | 电池"
                                if pure_code in full_map:
                                    # 如果还没加过 🔥，就加在最前面
                                    current_val = full_map[pure_code]
                                    if "🔥" not in current_val:
                                        full_map[pure_code] = f"🔥{board_name} | {current_val}"
                                    else:
                                        # 如果已经有火了，追加概念
                                        # "🔥固态电池 锂矿 | 电池"
                                        parts = current_val.split('|')
                                        hot_part = parts[0]
                                        base_part = parts[1] if len(parts) > 1 else ""
                                        if board_name not in hot_part:
                                            full_map[pure_code] = f"{hot_part} {board_name} | {base_part}"

                                    hot_info_count += 1

            # 存入上下文
            context['ths_hot_map'] = full_map
            print(f" ✅ (覆盖 {len(full_map)} 只, 热点叠加 {hot_info_count} 次)", end="")

            # === 3. 落盘保存 (修复路径) ===
            self._save_to_json(full_map)

        except Exception as e:
            print(f" {Fore.RED}❌ 异常: {e}{Fore.RESET}")

    def _save_to_json(self, data):
        try:
            # 动态获取项目根目录: 当前文件向上回溯 4 级
            # src/data/tushare_source/steps/ths_board.py -> src/data/tushare_source/steps -> ... -> project_root
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file)))))

            # 强制指向 data/output
            out_dir = os.path.join(project_root, 'data', 'output')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, 'ths_concept_map.json')

            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # print(f" -> {out_path}") # 路径太长就不打印了
        except Exception as e:
            print(f" -> ⚠️ 导出失败: {e}")

    def enrich(self, stock, row, context):
        if 'ths_hot_map' in context:
            concepts = context['ths_hot_map'].get(stock.code, "")
            if concepts:
                stock.ths_hot_concept = concepts