import pandas as pd

class BaseDataStep:
    """所有数据源插件的基类"""
    def __init__(self, pro):
        self.pro = pro

    # ✅ 修改：增加 **kwargs 接收 step_idx 和 total_steps
    def fetch(self, date_str: str, context: dict, **kwargs):
        """拉取数据存入 context"""
        pass

    def enrich(self, stock, row: pd.Series, context: dict):
        """从 context 读取数据并注入 Stock 对象"""
        pass