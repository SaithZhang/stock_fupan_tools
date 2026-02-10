import pandas as pd
from src.core.domain import Stock

class BaseDataStep:
    """所有数据源插件的基类"""
    def __init__(self, pro):
        self.pro = pro

    def fetch(self, date_str: str, context: dict):
        """拉取数据存入 context"""
        pass

    def enrich(self, stock: Stock, row: pd.Series, context: dict):
        """从 context 读取数据并注入 Stock 对象"""
        pass