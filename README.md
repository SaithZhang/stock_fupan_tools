# 🦅 股票复盘与监控系统 (Stock Review & Monitor System)

> **当前版本**: V4.1 (Stable / MoneyFlow Integrated)
> **核心驱动**: Tushare Pro + 策略流水线 + 盘中实时监控
> **架构模式**: Pipeline Pattern (流水线模式) + Domain Driven Design (领域驱动)

本工程用于 A 股短线交易的日常复盘、策略筛选及盘中监控。核心围绕 **“弱转强”**、**“龙头战法”** 及 **“资金流向”** 体系构建。

---

## 🚀 核心功能 (Features)

本项目已实现 **全自动化 Tushare 数据接入**。数据层采用 **流水线插件模式 (Pipeline)**，支持热插拔扩展。

| 数据模块 | 对应插件 (Step) | 功能说明 | 状态 |
| :--- | :--- | :--- | :--- |
| **基础行情** | `BasicInfoStep` | 日线、复权因子、昨收、量比计算 | ✅ |
| **云端竞价** | `AuctionStep` | **[核心]** 每日9:25自动拉取竞价涨幅、竞价金额、量比 | ✅ |
| **涨跌停** | `LimitBoardStep` | 同花顺涨跌停榜单、连板高度、炸板分析 | ✅ |
| **市场热度** | `SentimentStep` | 同花顺/东财 App 热榜 Top200 | ✅ |
| **资金流向** | `ThsMoneyFlowStep` | **[NEW]** 主力大单、资金净流入、5日主力增仓 | ✅ |
| **同花顺板块** | `ThsBoardStep` | **[NEW]** 行业与同花顺核心题材 (如"固态电池") | ✅ |
| **智能筹码** | `ChipStep` | 获利盘比例、成本支撑位测算 | ✅ |

---

## 🛠️ 开发者指南：如何扩展数据源 (Add New Data Source)

**这是本项目的核心扩展逻辑。** 当你需要增加新的 Tushare 接口（例如：北向资金、基本面数据、龙虎榜详情）时，请严格遵循以下 **4步流程**：

### 1. 定义数据模型 (Domain)
修改 `src/core/domain.py`。
在 `Stock` 类中明确定义你需要的字段，这样 IDE 会有提示，且导出时不会乱。

```python
@dataclass
class Stock:
    # ... 原有字段 ...
    
    # ✅ [Step 1] 新增你的字段
    hk_hold_amount: float = 0.0  # 北向持股金额
```

### 2. 编写采集插件 (Step)
在 `src/data/tushare_source/steps/` 下新建文件（例如 `north_hold.py`）。
继承 `BaseDataStep` 并实现 `fetch` 和 `enrich` 方法。

```python
class NorthHoldStep(BaseDataStep):
    def fetch(self, date_str, context, step_idx, total_steps):
        # 1. 调接口
        df = self.pro.hk_hold(trade_date=date_str)
        # 2. 转字典 (Key 建议用 ts_code, 如 000001.SZ)
        data_map = df.set_index('ts_code').to_dict('index')
        # 3. 存入上下文
        context['north_map'] = data_map

    def enrich(self, stock, row, context):
        # 4. 从上下文取出数据，注入 Stock 对象
        if 'north_map' in context:
            data = context['north_map'].get(stock.ts_code)
            if data:
                stock.hk_hold_amount = data.get('vol', 0)
```

### 3. 注册到流水线 (Pipeline)
修改 `src/data/tushare_source/pipeline.py`。
将你的 Step 加入 `self.steps` 列表。

```python
from src.data.tushare_source.steps.north_hold import NorthHoldStep # 导入

class StockDataPipeline:
    def __init__(self):
        self.steps = [
            BasicInfoStep(self.pro),
            # ... 其他步骤 ...
            NorthHoldStep(self.pro), # ✅ [Step 3] 注册在这里
        ]
```

### 4. 配置导出列 (Exporter)
修改 `src/data/exporter.py`。
将新字段加入 `priority_cols` 列表，确保它出现在 CSV 的前排显眼位置。

```python
priority_cols = [
    'code', 'name', 
    'hk_hold_amount', # ✅ [Step 4] 把它排在你想看的位置
    # ...
]
```

---

## 📂 项目结构 (Project Structure)

```plaintext
src/
├── config/              # 配置文件 (路径、API Token)
├── core/
│   ├── domain.py        # [核心] Stock 对象定义 (修改此处定义字段)
│   ├── pool_generator_tushare.py # [入口] 复盘程序主入口
│   └── filter.py        # 选股过滤器 (剔除ST、流动性差)
├── data/
│   ├── exporter.py      # [输出] CSV 导出控制器 (修改此处调整列顺序)
│   └── tushare_source/
│       ├── pipeline.py  # [引擎] 数据流水线管理器 (注册 Step)
│       └── steps/       # [插件] 所有数据采集脚本
│           ├── basic.py
│           ├── auction.py
│           ├── ths_moneyflow.py  # 资金流向插件
│           └── ...
└── strategies/          # 策略逻辑 (根据数据打标签)
```

---

## ⚡ 快速开始 (Quick Start)

### 1. 准备工作
确保 `src/config/settings.py` 中已配置 Tushare Token。

### 2. 执行复盘 (每日 15:30 后)
该脚本会自动拉取当日所有数据，生成策略池。

```bash
python src/core/pool_generator_tushare.py
```
> **输出文件**: `data/output/strategy_pool.csv`
> **包含数据**: 涨跌停、竞价强弱、主力资金流向、同花顺热点概念。

### 3. 盘中监控 (每日 9:25 - 9:30)
用于监控竞价弱转强标的。

```bash
python src/monitors/call_auction_screener.py
```

---

## 📊 策略标签说明

生成的 CSV 中 `tag` 列包含以下逻辑：

*   **💰 主力抢筹**: 主力大单净买入 > 5000万，且散户在卖出。
*   **🏦 五日资金红肥**: 连续5日主力资金净流入 > 1亿。
*   **👀 主力暗中吸筹**: 股价涨跌幅小 (-2%~3%)，但主力资金大幅净买入。
*   **🔥 竞价超预期**: 竞价涨幅 > 2% 且 量比 > 5。
*   **🛡️ 回踩成本线**: 股价回踩获利盘 5% 成本线，且未跌破。

---

> **Note**: 本项目严格遵循 **开闭原则 (Open-Closed Principle)**。新增功能请尽量通过增加 `Step` 类实现，避免修改 `pipeline.py` 的核心循环逻辑。