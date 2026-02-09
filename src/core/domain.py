# ==============================================================================
# 🧱 核心领域模型 (src/core/domain.py)
# 功能：定义标准化的股票数据结构，替代 loose dict
# ==============================================================================
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any


@dataclass
class Stock:
    # --- 身份信息 ---
    code: str  # 纯数字代码 (000001)
    name: str  # 股票名称
    ts_code: str  # Tushare代码 (000001.SZ)

    # --- 基础行情 (高频使用) ---
    price: float = 0.0  # 当前价 (close)
    open_price: float = 0.0  # 开盘价
    pct: float = 0.0  # 今日涨幅 (today_pct)
    open_pct: float = 0.0  # 开盘涨幅
    amount: float = 0.0  # 成交额 (元)
    turnover: float = 0.0  # 换手率
    vol_ratio: float = 0.0  # 量比

    # --- 竞价数据 (策略核心) ---
    auc_amt: float = 0.0  # 竞价成交额
    auc_pct: float = 0.0  # 竞价涨幅
    auc_ratio: float = 0.0  # 竞价量比 (竞价量/昨日全天量)
    call_auction_ratio: float = 0.0  # 冗余字段兼容导出 (通常 = auc_ratio * 100)

    # --- 涨跌停/板学 ---
    is_zt: bool = False  # 是否涨停
    is_dt: bool = False  # 是否跌停
    limit_days: int = 0  # 连板高度 (首板=1)
    limit_type: str = ""  # 板型 (T字/换手/一字)
    ths_status: str = ""  # 同花顺状态描述
    is_broken: bool = False  # 是否炸板
    ths_desc: str = ""  # 同花顺涨停原因

    # --- 扩展槽 (为未来大数据源预留) ---
    # 比如: 龙虎榜净买入、北向资金流向、板块名称
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- 策略打标结果 ---
    tags: List[str] = field(default_factory=list)
    risk_level: str = "🟢 Safe"  # 风险评级

    @property
    def sina_code(self):
        """自动生成新浪代码 sz000001"""
        market = self.ts_code.split('.')[-1].lower()
        return f"{market}{self.code}"

    @property
    def today_pct(self):
        """兼容旧代码 item['today_pct']"""
        return self.pct

    def add_tag(self, tag: str):
        if tag and tag not in self.tags:
            self.tags.append(tag)

    def to_dict(self):
        """导出为字典，用于 CSV 写入"""
        base = asdict(self)
        # 处理一些动态属性或重命名
        base['sina_code'] = self.sina_code
        base['tag'] = '/'.join(self.tags)
        base['limit_up_type'] = self.limit_type
        # 移除不必要的复杂对象
        del base['extra']
        del base['tags']
        return base

    # 🔥🔥🔥 核心兼容层 🔥🔥🔥
    # 这段代码让 Stock 对象可以像字典一样被访问 (stock['price'])
    # 这样你的旧策略代码就不需要立刻重写了！
    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.extra:
            return self.extra[key]
        # 兼容一些旧字段名映射
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