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

    # ✅ 新增：市值数据 (万元) ---
    circ_mv: float = 0.0  # 流通市值
    total_mv: float = 0.0  # 总市值

    # --- 竞价数据 ---
    auc_amt: float = 0.0
    auc_pct: float = 0.0
    auc_ratio: float = 0.0
    call_auction_ratio: float = 0.0

    # --- 状态标记 ---
    is_zt: bool = False
    is_dt: bool = False
    is_st: bool = False
    limit_days: int = 0
    limit_type: str = ""
    ths_status: str = ""
    is_broken: bool = False
    ths_desc: str = ""

    # --- 扩展槽 (用于存放未明确定义的临时数据) ---
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- 筹码分布数据 (Chip Distribution) ---
    winner_rate: float = 0.0  # 获利盘比例 (胜率)
    cost_5pct: float = 0.0  # 5分位成本 (底部支撑)
    cost_95pct: float = 0.0  # 95分位成本 (顶部压力)
    weight_avg: float = 0.0  # 加权平均成本

    # --- 资金流向数据 (Money Flow) ---
    mf_net_amount: float = 0.0  # 当日净流入 (万元)
    mf_lg_amount: float = 0.0  # 主力大单净流入 (万元)
    mf_d5_amount: float = 0.0  # 5日主力净流入 (万元)
    mf_sm_amount: float = 0.0  # 散户小单净流入 (万元)

    # --- 策略结果 ---
    tags: List[str] = field(default_factory=list)
    risk_level: str = "🟢 Safe"
    ths_hot_concept: str = ""  # 同花顺热门概念

    @property
    def sina_code(self):
        # 兼容处理：有些代码可能是 "000001.SZ"
        if '.' in self.ts_code:
            market = self.ts_code.split('.')[-1].lower()
            return f"{market}{self.code}"
        return f"sz{self.code}" if self.code.startswith('0') or self.code.startswith('3') else f"sh{self.code}"

    @property
    def today_pct(self):
        return self.pct

    def add_tag(self, tag: str):
        if tag and tag not in self.tags:
            self.tags.append(tag)

    def to_dict(self):
        """
        转换为字典，用于 DataFrame 生成或 JSON 序列化
        """
        # asdict 会自动把 dataclass 里定义的所有字段（包括新增的 circ_mv）都转成字典
        base = asdict(self)

        # 补充/覆盖一些计算字段
        base['today_pct'] = self.pct
        base['sina_code'] = self.sina_code
        base['tag'] = '/'.join(self.tags)
        base['limit_up_type'] = self.limit_type

        # 移除不需要导出的内部字段
        if 'extra' in base: del base['extra']
        if 'tags' in base: del base['tags']

        return base

    def __getitem__(self, key):
        """支持 stock['key'] 方式访问，兼容旧代码"""
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