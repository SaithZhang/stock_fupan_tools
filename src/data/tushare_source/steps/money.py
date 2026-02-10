# src/data/tushare_source/steps/money.py
from .base import BaseDataStep
import pandas as pd


class SmartMoneyStep(BaseDataStep):
    """
    [P5] 主力资金综合分析
    融合了：
    1. 🐉 知名游资明细 (hm_detail) - 追踪大佬
    2. 🏢 机构买卖明细 (top_inst) - 追踪机构趋势
    3. 📈 龙虎榜单 (top_list) - 获取上榜理由
    """

    def fetch(self, date_str, context):
        print(f"   ├── [5/6] 获取主力资金(游资/机构)...", end="", flush=True)

        # 1. 游资明细
        hm_map = {}
        try:
            df_hm = self.pro.hm_detail(trade_date=date_str)
            if not df_hm.empty:
                for _, r in df_hm.iterrows():
                    amt = float(r.get('net_amount', 0))
                    if abs(amt) < 5000000: continue  # 过滤小额

                    # 格式: 🐉陈小群买500w
                    action = f"{r['hm_name']}{'买' if amt > 0 else '卖'}{int(abs(amt) / 10000)}w"
                    code = r['ts_code']
                    if code not in hm_map: hm_map[code] = []
                    hm_map[code].append(action)
        except:
            pass

        # 2. 机构明细 (新增)
        inst_map = {}  # code -> net_buy
        try:
            df_inst = self.pro.top_inst(trade_date=date_str)
            if not df_inst.empty:
                # 机构可能有多个席位买卖，需按 code 聚合
                # side: 0=买入榜, 1=卖出榜 (top_inst 接口数据结构比较特殊，buy/sell 列本身就有值)
                # 我们直接用 buy - sell 计算净额
                df_inst['net'] = df_inst['buy'] - df_inst['sell']

                # 按代码分组求和
                inst_groups = df_inst.groupby('ts_code')['net'].sum()
                for code, net_amt in inst_groups.items():
                    inst_map[code] = net_amt
        except:
            pass

        # 3. 龙虎榜理由 (新增)
        reason_map = {}
        try:
            df_top = self.pro.top_list(trade_date=date_str)
            if not df_top.empty:
                # 去重，一只股票可能有多个上榜理由，取第一个即可
                for _, r in df_top.drop_duplicates('ts_code').iterrows():
                    reason = str(r['reason'])
                    # 简化理由文案
                    if '涨幅' in reason:
                        reason = '涨幅偏离'
                    elif '跌幅' in reason:
                        reason = '跌幅偏离'
                    elif '换手' in reason:
                        reason = '高换手'
                    elif '振幅' in reason:
                        reason = '高振幅'
                    elif '连续' in reason:
                        reason = '连板异动'
                    reason_map[r['ts_code']] = reason
        except:
            pass

        # 存入上下文
        context['hm_map'] = hm_map
        context['inst_map'] = inst_map
        context['reason_map'] = reason_map

        count = len(hm_map) + len(inst_map)
        print(f" ✅ (游资{len(hm_map)}/机构{len(inst_map)})")

    def enrich(self, stock, row, context):
        # 1. 注入游资标签
        hm_actions = context.get('hm_map', {}).get(stock.ts_code)
        if hm_actions:
            for act in hm_actions: stock.add_tag(f"🐉{act}")

        # 2. 注入机构标签
        inst_net = context.get('inst_map', {}).get(stock.ts_code, 0)
        if inst_net > 30000000:  # 净买入 > 3000万
            stock.add_tag("🏢机构爆买")
        elif inst_net > 10000000:  # 净买入 > 1000万
            stock.add_tag("🏢机构大买")
        elif inst_net < -20000000:  # 净卖出 > 2000万
            stock.add_tag("💀机构出逃")

        # 3. 注入上榜理由
        reason = context.get('reason_map', {}).get(stock.ts_code)
        if reason:
            stock.add_tag(f"榜:{reason}")