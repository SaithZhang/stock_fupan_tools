# src/data/tushare_source/steps/t_trade.py

from .base import BaseDataStep
from src.core.t_trader import TTraderAssistant
from src.config.settings import Config
from src.utils.text_tools import TextUtils
from colorama import Fore


class TTradeStep(BaseDataStep):
    """
    [P7] 做T辅助分析 (仅针对持仓)
    描述: 调用 TTraderAssistant 计算支撑压力位、异动风险
    """

    def __init__(self, pro):
        super().__init__(pro)
        # 初始化核心分析器
        self.analyzer = TTraderAssistant()
        self.holdings = set()

    def fetch(self, date_str, context, step_idx=0, total_steps=0, **kwargs):
        """
        准备阶段: 加载持仓列表
        """
        prefix = f"[{step_idx}/{total_steps}]" if total_steps > 0 else "[?/?]"
        print(f"   ├── {prefix} 加载持仓做T策略...", end="", flush=True)

        # 从配置或文件中读取持仓代码 (兼容 600000 和 600000.SH)
        # 假设 TextUtils.load_text_list 返回的是 ['600000', '000001']
        raw_holdings = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.holdings = set(code.split('.')[0] for code in raw_holdings)

        # 将持仓信息放入上下文，供后续 verify 使用 (可选)
        context['holdings_set'] = self.holdings

        print(f" ✅ (监控 {len(self.holdings)} 只持仓)")

    def enrich(self, stock, row, context):
        """
        增强阶段: 仅对持仓股调用昂贵的分钟线接口
        """
        # 🎯 核心过滤: 非持仓股直接跳过，节省大量时间与积分
        if stock.code not in self.holdings:
            return

        try:
            # print(f"      >> 分析持仓: {stock.name}...", end="\r")

            # 调用核心算法 (上一步我们写的 TTraderAssistant)
            # 传入当前价格 (stock.price 是 row['close'])
            analysis_result = self.analyzer.analyze(
                ts_code=stock.ts_code,
                current_price=stock.price
            )

            # 将结果动态注入到 Stock 对象中
            # 建议在 Stock 对象里专门开辟一个属性，或者直接打平属性
            if analysis_result:
                # 方案 A: 注入到一个字典属性 (建议)
                stock.t_data = analysis_result

                # 方案 B: 也可以直接挂载到 extra_info (如果你的 Stock 类有这个)
                # if hasattr(stock, 'extra_info'):
                #     stock.extra_info.update(analysis_result)

                # 为了方便后续导出，也可以动态设置属性
                for k, v in analysis_result.items():
                    setattr(stock, k, v)

        except Exception as e:
            print(f"{Fore.RED} [做T分析错误] {stock.name}: {e}{Fore.RESET}")