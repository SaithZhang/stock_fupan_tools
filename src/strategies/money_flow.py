from src.strategies.interface import Strategy
from src.core.domain import Stock


class MoneyFlowStrategy(Strategy):
    """
    同花顺资金流向策略 (V2.0 修正版)
    核心逻辑：寻找主力大举买入且散户卖出的标的
    """

    def run(self, stock: Stock) -> list:
        tags = []

        # 0. 安全检查：确保资金字段存在且不为0 (避免没数据时乱打标签)
        if not hasattr(stock, 'mf_lg_amount') or stock.mf_lg_amount == 0:
            return tags

        # 1. 基础数据准备 (单位统一处理)
        # Tushare/同花顺通常返回单位是 [万元]
        # 1亿 = 10000 万元
        lg_amount = stock.mf_lg_amount  # 主力大单净额
        sm_amount = stock.mf_sm_amount  # 散户小单净额
        d5_amount = stock.mf_d5_amount  # 5日主力净额

        # 兼容处理涨跌幅字段 (Stock对象里通常叫 pct)
        pct = getattr(stock, 'pct', getattr(stock, 'pct_change', 0.0))

        # --- 阈值设定 (建议根据实际市场热度微调) ---
        # 5000万元 = 0.5亿
        THRESHOLD_STRONG = 5000
        # 2000万元 = 0.2亿 (用于暗中吸筹)
        THRESHOLD_HIDDEN = 2000
        # 1亿元 (5日累计)
        THRESHOLD_D5 = 10000

        # =======================
        # 🏷️ 策略逻辑分支
        # =======================

        # 1. [强] 主力暴力抢筹
        # 逻辑：大单大幅流入 + 散户大幅流出 (散户交出筹码)
        if lg_amount > THRESHOLD_STRONG and sm_amount < 0:
            # 修正：/10000 换算为亿，保留1位小数
            amount_yi = lg_amount / 10000
            tags.append(f"💰主力抢筹({amount_yi:.1f}亿)")

        # 2. [中] 隐蔽吸筹 / 震荡洗盘
        # 逻辑：股价波动很小 (-2% ~ 3%)，但主力资金在买，散户在卖
        if -2 < pct < 3:
            if lg_amount > THRESHOLD_HIDDEN and sm_amount < -THRESHOLD_HIDDEN / 2:
                tags.append("👀主力暗中吸筹")

        # 3. [妖] 逆势护盘 (高胜率信号) [Image of divergence trading strategy]
        # 逻辑：股价是绿的 (下跌)，但主力大单是红的 (净买入) -> 背离
        if pct < 0 and lg_amount > THRESHOLD_STRONG:
            tags.append("🚩主力逆势护盘")

        # 4. [稳] 趋势资金 (中线逻辑)
        if d5_amount > THRESHOLD_D5:
            tags.append("🏦五日资金红肥")

        # 5. [危] 拉高出货预警
        # 逻辑：股价大涨 > 6%，但主力大单疯狂流出 (比如流出超3000万)
        # 这通常是主力利用涨停板或大阳线在派发筹码给散户
        if pct > 6 and lg_amount < -3000:
            tags.append("⚠️拉高出货嫌疑")

        return tags