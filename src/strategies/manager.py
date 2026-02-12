# ==============================================================================
# 🧠 策略管理器 (src/strategies/manager.py)
# ==============================================================================
import pandas as pd
from typing import List
from src.core.domain import Stock

# 1. 导入标准接口
from src.strategies.interface import Strategy

# 2. 导入具体策略模块
# (请确保文件名和类名与实际一致)
from src.strategies.technical import (
    TrendStrategy,
    ReboundStrategy,
    DDDStrategy,
    SidewaysChipStrategy
)
from src.strategies.sentiment import (
    IdentityStrategy,
    LHBStrategy
)
from src.strategies.bolao_chip_strategy import BoLaoChipStrategy
from src.strategies.money_flow import MoneyFlowStrategy # 新增

class StrategyManager:
    def __init__(self):
        # 在此注册所有启用的策略
        # 顺序不影响逻辑，但影响标签显示的先后顺序
        self.strategies: List[Strategy] = [
            # --- 基础技术面 ---
            TrendStrategy(),  # 均线多头
            ReboundStrategy(),  # 回踩支撑
            DDDStrategy(),  # 放量/量比
            SidewaysChipStrategy(),  # 长期横盘(价格形态)

            # --- 情绪/玄学 ---
            IdentityStrategy(),  # 名字玄学
            LHBStrategy(),  # 龙虎榜

            # --- 核心筹码博弈 ---
            BoLaoChipStrategy(), # 拨佬筹码突破/支撑
            # --- 新增资金策略 ---
            MoneyFlowStrategy()
        ]

    def run_all(self, stocks: List[Stock]) -> pd.DataFrame:
        """
        对股票池运行所有策略，返回分析结果 DataFrame
        """
        if not stocks:
            print("⚠️ 股票池为空，跳过策略分析。")
            return pd.DataFrame()

        print(f"🧠 正在调用 {len(self.strategies)} 个策略模型分析 {len(stocks)} 只股票...")

        results = []
        for stock in stocks:
            # 将对象转换为字典，方便处理 (如果 stock 本身就是 dict 则直接用)
            row = stock.__dict__.copy() if hasattr(stock, '__dict__') else stock.copy()

            all_tags = []

            # 遍历每个策略，收集标签
            for strategy in self.strategies:
                try:
                    tags = strategy.run(stock)
                    if tags:
                        all_tags.extend(tags)
                except Exception as e:
                    # 某个策略报错不应阻断整体流程，打印日志即可
                    print(f"❌ 策略 {strategy.__class__.__name__} 报错: {e}")

            # 合并标签：用 " | " 分隔
            row['tag'] = " | ".join(all_tags) if all_tags else ""

            # 记录命中的策略数量 (可选，用于后续筛选“多重共振”的标的)
            row['strategy_count'] = len(all_tags)

            results.append(row)

        df = pd.DataFrame(results)
        print("✅ 策略分析完成！")

        return df