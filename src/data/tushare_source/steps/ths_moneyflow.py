import pandas as pd
from colorama import Fore
from src.data.tushare_source.steps.base import BaseDataStep


class ThsMoneyFlowStep(BaseDataStep):
    """
    [P8] 同花顺个股资金流向
    功能：获取主力、大单、中单、小单的资金流向
    门槛：5000积分
    """

    def fetch(self, date_str: str, context: dict, step_idx=0, total_steps=0):
        # 动态打印步骤
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[8/?]"
        print(f"   ├── {prefix} 正在分析主力资金流向...", end="", flush=True)

        try:
            # 1. 调取接口
            df = self.pro.moneyflow_ths(trade_date=date_str)

            if df.empty:
                print(f" {Fore.YELLOW}⚠️ 无数据 (可能需5000积分或非交易日){Fore.RESET}")
                return

            # 2. 转为字典映射 (关键：使用 ts_code 作为 key)
            # key: '000001.SZ', value: { ... }
            flow_map = df.set_index('ts_code')[
                ['net_amount', 'net_d5_amount', 'buy_lg_amount', 'buy_sm_amount']
            ].to_dict('index')

            # 3. 存入上下文
            context['money_flow_map'] = flow_map
            print(f" ✅ (获取 {len(df)} 条)")

        except Exception as e:
            print(f" {Fore.RED}❌ 接口报错: {e}{Fore.RESET}")

    def enrich(self, stock, row, context):
        """将资金数据绑定到 Stock 对象上"""
        if 'money_flow_map' in context:
            # 🔍 核心修复：双重匹配机制
            # 1. 先试 ts_code (000001.SZ) - 这是 Tushare 标准，最准
            data = context['money_flow_map'].get(stock.ts_code)

            # 2. 如果没取到，再试 code (000001) - 防止数据源格式不一致
            if not data:
                data = context['money_flow_map'].get(stock.code)

            # 3. 赋值 (注意：Tushare 返回的是 '万元')
            if data:
                stock.mf_net_amount = float(data.get('net_amount', 0))
                stock.mf_lg_amount = float(data.get('buy_lg_amount', 0))
                stock.mf_d5_amount = float(data.get('net_d5_amount', 0))
                stock.mf_sm_amount = float(data.get('buy_sm_amount', 0))
            else:
                # 显式赋值为 0
                stock.mf_net_amount = 0.0
                stock.mf_lg_amount = 0.0
                stock.mf_d5_amount = 0.0
                stock.mf_sm_amount = 0.0