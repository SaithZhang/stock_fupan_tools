# ==============================================================================
# 🧱 核心领域模型 (src/core/domain.py)
# ==============================================================================
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any


@dataclass
class Stock:
    # --- 身份信息 ---
    code: str
    name: str
    ts_code: str

    # --- 基础行情 ---
    price: float = 0.0
    open_price: float = 0.0
    pct: float = 0.0
    open_pct: float = 0.0
    amount: float = 0.0
    turnover: float = 0.0
    vol_ratio: float = 0.0

    # --- 竞价数据 ---
    auc_amt: float = 0.0
    auc_pct: float = 0.0
    auc_ratio: float = 0.0
    call_auction_ratio: float = 0.0

    # --- 状态标记 ---
    is_zt: bool = False
    is_dt: bool = False
    is_st: bool = False  # ✅ 新增：是否ST股
    limit_days: int = 0
    limit_type: str = ""
    ths_status: str = ""
    is_broken: bool = False
    ths_desc: str = ""

    # --- 扩展槽 ---
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- 新增：筹码分布数据 (Chip Distribution) ---
    winner_rate: float = 0.0  # 获利盘比例 (胜率)
    cost_5pct: float = 0.0  # 5分位成本 (底部支撑)
    cost_95pct: float = 0.0  # 95分位成本 (顶部压力/突破位)
    weight_avg: float = 0.0  # 加权平均成本 (全市场平均持仓成本)

    # ✅ 新增：资金流向数据 (Money Flow) ---
    mf_net_amount: float = 0.0  # 当日净流入 (万元)
    mf_lg_amount: float = 0.0  # 主力大单净流入 (万元)
    mf_d5_amount: float = 0.0  # 5日主力净流入 (万元)
    mf_sm_amount: float = 0.0  # 散户小单净流入 (万元)

    # --- 策略结果 ---
    tags: List[str] = field(default_factory=list)
    risk_level: str = "🟢 Safe"

    # 新增字段 (默认空字符串)
    ths_hot_concept: str = ""

    @property
    def sina_code(self):
        market = self.ts_code.split('.')[-1].lower()
        return f"{market}{self.code}"

    @property
    def today_pct(self):
        return self.pct

    def add_tag(self, tag: str):
        if tag and tag not in self.tags:
            self.tags.append(tag)

    def to_dict(self):
        base = asdict(self)
        base['today_pct'] = self.pct
        base['sina_code'] = self.sina_code
        base['tag'] = '/'.join(self.tags)
        base['limit_up_type'] = self.limit_type
        del base['extra']
        del base['tags']
        return base

    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.extra:
            return self.extra[key]
        if key == 'today_pct': return self.pct
        if key == 'auction_ratio': return self.auc_ratio
        return None

    def get(self, key, default=None):
        val = self.__getitem__(key)
        return val if val is not None else default

    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.extra[key] = value