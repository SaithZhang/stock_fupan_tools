import re
from dataclasses import dataclass
from typing import Set

@dataclass
class LiveStockContext:
    """盘中个股上下文：封装所有评估所需数据，彻底消灭散装变量"""
    code: str
    name: str
    open_pct: float
    real_pct: float
    auc_amt: float
    yest_pct: float
    last_amt: float
    circ_mv: float
    boards: int
    industry: str
    pool_tag: str
    is_holding: bool
    is_focus: bool
    limit_up_concepts: Set[str]  # 全局当日一字板概念集合

    @property
    def my_concepts(self) -> Set[str]:
        """解析自身的概念集合"""
        return set([c.strip() for c in re.split(r'[/+,-]', self.industry) if c.strip()])

    @property
    def has_limit_up_brother(self) -> bool:
        """判断是否有同概念小弟顶了一字板"""
        return bool(self.my_concepts.intersection(self.limit_up_concepts))