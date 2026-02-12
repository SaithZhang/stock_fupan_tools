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
        print(f"   ├── [{step_idx}/{total_steps}] 正在分析主力资金流向...", end="", flush=True)

        try:
            # 1. 调取接口 (单次最大6000条，足够覆盖全市场)
            df = self.pro.moneyflow_ths(trade_date=date_str)

            if df.empty:
                print(f" {Fore.YELLOW}⚠️ 无数据 (可能需5000积分或非交易日){Fore.RESET}")
                return

            # 2. 转为字典映射，方便快速查找
            # key: code, value: dict of flow data
            flow_map = df.set_index('ts_code')[
                ['net_amount', 'net_d5_amount', 'buy_lg_amount', 'buy_sm_amount']
            ].to_dict('index')

            # 3. 存入上下文
            context['money_flow_map'] = flow_map
            print(f" ✅ (获取 {len(df)} 条资金数据)")

        except Exception as e:
            print(f" {Fore.RED}❌ 接口报错: {e}{Fore.RESET}")

    def enrich(self, stock, row, context):
        """将资金数据绑定到 Stock 对象上"""
        if 'money_flow_map' in context:
            data = context['money_flow_map'].get(stock.code)
            if data:
                # 挂载属性 (单位：万元)
                stock.mf_net_amount = data.get('net_amount', 0)  # 当日净流入
                stock.mf_d5_amount = data.get('net_d5_amount', 0)  # 5日主力净额
                stock.mf_lg_amount = data.get('buy_lg_amount', 0)  # 今日大单(主力)
                stock.mf_sm_amount = data.get('buy_sm_amount', 0)  # 今日小单(散户)
            else:
                # 默认值
                stock.mf_net_amount = 0
                stock.mf_d5_amount = 0
                stock.mf_lg_amount = 0
                stock.mf_sm_amount = 0