# ==============================================================================
# ⚔️ 策略标准接口 (src/strategies/interface.py)
# ==============================================================================
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from src.core.domain import Stock

class Strategy(ABC):
    @abstractmethod
    def run(self, stock: Union[Stock, dict]) -> List[str]:
        """
        核心逻辑
        :param stock: 标准化的股票对象 (为了兼容，暂允许 dict)
        :return: 命中的标签列表 (如 ['趋势加速', '5日线低吸'])
        """
        pass