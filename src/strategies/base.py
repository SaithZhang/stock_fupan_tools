# ==============================================================================
# 🧬 策略基类 (src/strategies/base.py)
# 定义所有策略必须实现的接口
# ==============================================================================

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class BaseStrategy(ABC):
    """
    策略抽象基类。
    所有的策略（如F佬策略、打板策略、低吸策略）都必须继承此类。
    """

    @abstractmethod
    def run(self, item: Dict) -> List[str]:
        """
        执行策略逻辑
        :param item: 单只股票的清洗后数据 (包含 code, name, pct, amount 等)
        :return: 命中的标签列表 (e.g. ['F佬/关注', '5日线低吸'])。未命中返回空列表 []。
        """
        pass