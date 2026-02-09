# ==============================================================================
# 💎 拨佬筹码博弈策略 (src/strategies/bolao_chip_strategy.py)
# ==============================================================================
from typing import List, Union
from src.core.domain import Stock
from src.strategies.interface import Strategy


class BoLaoChipStrategy(Strategy):
    """
    【拨佬心法 - 筹码篇】
    核心逻辑：
    1. 趋势与支撑：平均成本线(weight_avg)是比5日线更真实的“全市场成本”，回踩不破为强支撑。
    2. 突破与空间：股价突破95%筹码成本(cost_95pct)，上方无套牢盘，进入“天空海阔”模式。
    3. 风险与出货：高获利盘(winner_rate>90%) + 高换手 = 主力高位兑现。
    """

    def run(self, stock: Union[Stock, dict]) -> List[str]:
        labels = []

        # 使用基类提供的安全取值方法
        price = self.get_val(stock, 'price')
        pct = self.get_val(stock, 'pct')
        turnover = self.get_val(stock, 'turnover')

        # 筹码数据 (确保 fetcher 已经注入了这些字段)
        winner_rate = self.get_val(stock, 'winner_rate')
        cost_avg = self.get_val(stock, 'weight_avg')
        cost_95 = self.get_val(stock, 'cost_95pct')

        # 数据有效性检查
        if price == 0 or cost_avg == 0:
            return []

        # ------------------------------------------------------------------
        # 1. 筹码突破 (天空海阔)
        # ------------------------------------------------------------------
        if price > cost_95:
            # 缩量加速：胜率高，换手低，涨幅大
            if winner_rate > 90 and turnover < 10 and pct > 5:
                labels.append(f"🔒锁仓加速(胜率{int(winner_rate)}%)")
            # 普通突破
            elif winner_rate > 80:
                labels.append(f"🚀筹码突破(胜率{int(winner_rate)}%)")

        # ------------------------------------------------------------------
        # 2. 平均成本支撑 (趋势低吸)
        # ------------------------------------------------------------------
        # 股价回踩全市场平均成本线附近 (0% ~ 3% 偏差)
        dist_to_avg = (price - cost_avg) / cost_avg * 100
        if 0 < dist_to_avg < 3 and pct > -2:
            labels.append("🛡️回踩成本线支撑")

        # ------------------------------------------------------------------
        # 3. 高位分歧/出货预警
        # ------------------------------------------------------------------
        # 获利盘极高 + 换手极大 = 主力出货或剧烈博弈
        if winner_rate > 85 and turnover > 20:
            if pct < 0:
                labels.append(f"⚠️高位获利兑现(换手{int(turnover)}%)")
            else:
                labels.append(f"💣高位剧烈博弈(换手{int(turnover)}%)")

        return labels