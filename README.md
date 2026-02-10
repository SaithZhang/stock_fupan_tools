# 🦅 股票复盘与监控系统 (Stock Review & Monitor System)

> **当前版本**: V4.0 (Modular Architecture / Tushare Automated)
> **核心驱动**: Tushare Pro + 策略流水线 + 盘中实时监控
> **设计理念**: 领域驱动设计 (DDD) + 插件化架构 (Pipeline Pattern) + 开闭原则 (OCP)

本工程用于 A 股短线交易的日常复盘、策略筛选及盘中监控。核心围绕 **“弱转强”**、**“龙头战法”** 及 **“监管风控”** 体系构建。

---

## 🚀 核心功能 (Features)

本项目已实现 **全自动化 Tushare 数据接入**，告别手动导出数据。数据层采用流水线插件模式，支持灵活扩展。

| 数据模块 | 对应插件 (Step) | 功能说明 | 状态 |
| :--- | :--- | :--- | :--- |
| **基础行情** | `BasicInfoStep` | 日线、复权因子、昨收、量比计算 | ✅ |
| **云端竞价** | `AuctionStep` | **[核心]** 每日9:25自动拉取竞价涨幅、竞价金额、量比 | ✅ |
| **涨跌停** | `LimitBoardStep` | 同花顺涨跌停榜单、连板高度、炸板分析 | ✅ |
| **市场热度** | `SentimentStep` | **[NEW]** 同花顺/东财 App 热榜 Top200 | ✅ |
| **游资明细** | `SmartMoneyStep` | **[NEW]** 知名游资（如陈小群、六一中路）操作明细 | ✅ |
| **筹码分布** | `ChipStep` | **[NEW]** 全市场获利盘比例、平均成本（盘后19:30更新） | ✅ |
| **大盘全景** | `MarketOverview` | 指数涨跌、涨跌家数统计、赚钱效应分析 | ✅ |

---

## 💻 架构与开发规范 (Architecture & Standards)

为了保持代码的长期可维护性，本项目严格遵循 **开闭原则 (Open/Closed Principle)**。

### 1. 目录结构 (Project Structure)

src/
├── core/
│   ├── pool_generator_tushare.py # [Client] 每日复盘策略工厂入口
│   ├── domain.py                 # [Domain] 领域对象 (Stock) 定义
│   └── filter.py                 # [Service] 选股过滤器 (黑名单/ST/市值)
└── data/
    └── tushare_source/           # [Infrastructure] 数据层
        ├── fetcher.py            # [Facade] 门面模式，唯一的外部访问入口
        ├── pipeline.py           # [Engine] 个股数据处理流水线
        ├── global_data.py        # [Service] 大盘/宏观数据服务
        └── steps/                # [Plugins] 数据源插件包 (新增数据源改这里)
            ├── base.py           # [Interface] 定义 fetch/enrich 接口
            ├── basic.py          # 基础行情插件
            ├── auction.py        # 竞价数据插件
            ├── sentiment.py      # 情绪热度插件
            └── ...               # (在此添加新文件)

### 2. 扩展指南：如何新增数据源？

如果您需要接入新的 Tushare 接口（例如“北向资金”），请遵循以下步骤，**无需修改 `fetcher.py` 或 `pipeline.py`**：

1.  **新建插件文件**：在 `src/data/tushare_source/steps/` 下新建 `north.py`。
2.  **继承基类实现接口**：
    from .base import BaseDataStep

    class NorthMoneyStep(BaseDataStep):
        def fetch(self, date_str, context):
            # 1. 拉取数据
            df = self.pro.hk_hold(trade_date=date_str)
            # 2. 存入上下文 (context 是一个共享字典)
            context['north_df'] = df

        def enrich(self, stock, row, context):
            # 3. 将数据注入 Stock 对象
            if stock.ts_code in context['north_df']:
                stock.add_tag("北向买入")

3.  **注册插件**：在 `src/data/tushare_source/pipeline.py` 的 `self.steps` 列表中添加 `NorthMoneyStep(self.pro)`。

### 3. 设计模式应用 (Design Patterns)

* **Facade Pattern (门面模式)**: `TushareFetcher` 是数据层的唯一入口，屏蔽了内部 `pipeline` 和 `global_data` 的复杂性。
* **Pipeline Pattern (流水线模式)**: 个股数据构建过程被拆分为多个独立的 `Step`，依次执行 `fetch` -> `merge` -> `enrich`。
* **Context Object (上下文对象)**: 使用 `ctx (dict)` 在各个 Step 之间传递 DataFrame，实现组件解耦。

---

## 🕒 每日作业流程 (Workflow)

### 1. 盘后复盘 (17:00 - 20:00)

目标：生成明日的 **策略池 (Strategy Pool)**。

1.  **准备配置**:
    * 确认 `Config.HOLDINGS_PATH` (持仓) 和 `Config.F_LAO_PATH` (关注池) 已更新。
    * 确保 Tushare Token 有效。

2.  **运行生成器**:
    python src/core/pool_generator_tushare.py

    * **程序动作**:
        1.  调用 `MarketOverview` 获取大盘指数与涨跌停统计。
        2.  启动 `StockDataPipeline`，流水线式拉取并清洗全市场个股数据。
        3.  `StockFilter` 剔除 ST、流动性差（成交额 < 5000万）的标的。
        4.  `StockTagger` 自动打标（如 "3天2板", "🔥Top10", "🐉陈小群买入"）。
    * **输出**: `data/output/strategy_pool.csv`

### 2. 竞价筛选 (9:25 - 9:30)

目标：锁定 **“弱转强”** 标的。

1.  **运行监控**:
    python src/monitors/call_auction_screener.py

2.  **核心策略**:
    * **🔥 弱转强**: 昨日分歧（烂板/断板/大阴） -> 今日 **高开 + 爆量**。
    * **💰 抢筹**: 竞价金额 > 1亿，或量比 > 10。
    * **📉 避雷**: 竞价跌幅 < -5%，核按钮预警。

### 3. 盘中盯盘 (9:30 - 15:00)

1.  **运行监控**:
    python src/monitors/intraday_monitor.py

    * 实时监控持仓盈亏。
    * 监控策略池中的“大单点火”信号。

---

## 📝 配置说明 (Configuration)

* `src/config/settings.py`:
    * `TUSHARE_TOKEN`: 您的 Tushare 密钥。
    * `THS_HOT_LIMIT`: 热榜抓取数量（默认 200）。
* `data/input/holdings.txt`: 持仓代码列表（每行一个代码）。
* `data/input/f_lao_list.txt`: 重点跟踪代码池。

---

## 🛠️ 模块索引 (Module Index)

| 模块路径 | 说明 |
| :--- | :--- |
| `src/core/pool_generator_tushare.py` | **【主程序】** 策略工厂入口 |
| `src/data/tushare_source/fetcher.py` | **【门面】** 数据层统一入口 |
| `src/data/tushare_source/pipeline.py` | **【引擎】** 个股数据处理流水线 |
| `src/data/tushare_source/global_data.py` | **【服务】** 大盘/宏观数据服务 |
| `src/data/tushare_source/steps/*.py` | **【插件】** 各种具体的数据源实现 |
| `src/monitors/call_auction_screener.py` | **【监控】** 竞价筛选工具 |
| `src/strategies/auction.py` | **【策略】** 竞价强弱判定逻辑 |