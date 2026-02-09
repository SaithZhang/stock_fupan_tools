# ==============================================================================
# ⚔️ 策略标准接口 (src/strategies/interface.py)
# ==============================================================================
from abc import ABC, abstractmethod
from typing import List, Union
from src.core.domain import Stock

class Strategy(ABC):
    @abstractmethod
    def run(self, stock: Union[Stock, dict]) -> List[str]:
        """
        核心执行逻辑
        :param stock: 股票对象 或 字典数据
        :return: 命中的标签列表，例如 ['趋势加速', '5日线低吸']。如果没有命中，返回空列表 []
        """
        pass

    # --- 通用辅助方法 (方便子类取值) ---
    def get_val(self, stock: Union[Stock, dict], key: str, default=0.0) -> float:
        """安全获取浮点数值"""
        if isinstance(stock, dict):
            return float(stock.get(key, default))
        return float(getattr(stock, key, default))

    def get_str(self, stock: Union[Stock, dict], key: str, default="") -> str:
        """安全获取字符串值"""
        if isinstance(stock, dict):
            return str(stock.get(key, default))
        return str(getattr(stock, key, default))