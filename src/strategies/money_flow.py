from src.strategies.interface import Strategy
from src.core.domain import Stock


class MoneyFlowStrategy(Strategy):
    """
    同花顺资金流向策略
    核心逻辑：寻找主力大举买入且散户卖出的标的
    """

    def run(self, stock: Stock) -> list:
        tags = []

        # 确保数据存在 (防止没积分或没数据时报错)
        if not hasattr(stock, 'mf_lg_amount'):
            return tags

        # 阈值设定 (单位：万元)
        BIG_MONEY_THRESHOLD = 5000  # 大单净流入 > 5000万 (强主力)
        D5_ACCUMULATE = 10000  # 5日累计流入 > 1亿 (持续吸筹)

        # 1. 主力强攻信号
        # 逻辑：大单大幅流入 + 散户流出 (筹码交换良性)
        if stock.mf_lg_amount > BIG_MONEY_THRESHOLD and stock.mf_sm_amount < 0:
            tags.append(f"💰主力抢筹({int(stock.mf_lg_amount / 100)}亿)")

        # 2. 隐蔽吸筹信号
        # 逻辑：当日股价没怎么涨(比如涨幅<3%)，但主力资金在买
        # 需要结合 stock.pct_change (假设你有这个字段)
        if hasattr(stock, 'pct_change') and -2 < stock.pct_change < 3:
            if stock.mf_lg_amount > 2000 and stock.mf_sm_amount < -1000:
                tags.append("👀主力暗中吸筹")

        # 3. 趋势护盘信号
        # 逻辑：5日主力资金持续为正
        if stock.mf_d5_amount > D5_ACCUMULATE:
            tags.append("🏦五日资金红肥")

        # 4. 警惕信号 (可选)
        # 股价大涨 > 5%，但主力资金流出 > 3000万 (拉高出货)
        if hasattr(stock, 'pct_change') and stock.pct_change > 5:
            if stock.mf_lg_amount < -3000:
                tags.append("⚠️拉高出货嫌疑")

        return tags