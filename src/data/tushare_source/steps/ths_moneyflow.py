# src/data/tushare_source/steps/ths_moneyflow.py

import pandas as pd
from colorama import Fore
from src.data.tushare_source.steps.base import BaseDataStep


class ThsMoneyFlowStep(BaseDataStep):
    """
    [P8] 同花顺个股资金流向
    """

    def fetch(self, date_str: str, context: dict, step_idx=0, total_steps=0):
        # ... fetch 部分保持不变 ...
        # 重点是这里：确保 flow_map 的 key 是 '000001.SZ' 这种格式
        try:
            df = self.pro.moneyflow_ths(trade_date=date_str)
            if df.empty:
                print(f" {Fore.YELLOW}⚠️ 无资金数据{Fore.RESET}")
                return

            # 使用 ts_code 作为 key
            flow_map = df.set_index('ts_code')[
                ['net_amount', 'net_d5_amount', 'buy_lg_amount', 'buy_sm_amount']
            ].to_dict('index')

            context['money_flow_map'] = flow_map
            print(f" ✅ (获取 {len(df)} 条)")

        except Exception as e:
            print(f" {Fore.RED}❌ 接口报错: {e}{Fore.RESET}")

    def enrich(self, stock, row, context):
        """将资金数据绑定到 Stock 对象上"""
        if 'money_flow_map' in context:
            # 🔍 核心修复：双重匹配机制
            # 1. 先试 ts_code (000001.SZ) - 这是最准的
            data = context['money_flow_map'].get(stock.ts_code)

            # 2. 如果没取到，再试 code (000001) - 防止某些特殊情况
            if not data:
                data = context['money_flow_map'].get(stock.code)

            # 3. 赋值 (注意：Tushare 返回的是 '万元')
            if data:
                stock.mf_net_amount = float(data.get('net_amount', 0))
                stock.mf_lg_amount = float(data.get('buy_lg_amount', 0))
                stock.mf_d5_amount = float(data.get('net_d5_amount', 0))
                stock.mf_sm_amount = float(data.get('buy_sm_amount', 0))
            else:
                # 显式赋值为 0，防止变成 None
                stock.mf_net_amount = 0.0
                stock.mf_lg_amount = 0.0
                stock.mf_d5_amount = 0.0
                stock.mf_sm_amount = 0.0