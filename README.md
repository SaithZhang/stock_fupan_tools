# 🦅 股票复盘与监控系统 (Stock Review & Monitor System)

> **当前版本**: V3.4 (Cloud Auction: Fully Automated)
> **核心驱动**: Tushare Pro + 策略工厂 + 盘中实时监控

本工程用于 A 股短线交易的日常复盘、策略筛选及盘中监控。核心围绕 **“弱转强”**、**“龙头战法”** 及 **“监管风控”** 体系构建。

---

## 🚀 核心功能与数据源 (Data & Features)

本项目正在从“手动导出数据”向“全自动化 Tushare 接口”转型。以下是当前接入的核心数据源：

| 数据类型 | 来源 | 说明 | 状态 |
| :--- | :--- | :--- | :--- |
| **基础行情** | 🦅 Tushare | 日线、复权因子、停复牌信息 | ✅ 已接入 |
| **云端竞价** | 🦅 Tushare | **[核心]** 每日9:25自动拉取全市场竞价数据 (量比/金额/涨幅) | ✅ **[NEW]** |
| **涨跌停分析**| 🦅 Tushare | 同花顺涨跌停榜单、连板高度、炸板数据 | ✅ 已接入 |
| **筹码分布** | 🦅 Tushare | 全市场获利盘比例 (`winner_rate`)、平均成本 | ⚠️ **[NEW]** (盘后需19:30更新) |
| **龙虎榜** | 🦅 Tushare | 每日上榜席位数据 (`top_list`)，识别游资/机构动向 | ✅ **[NEW]** |
| **监管风控** | 🦅 Tushare | (计划中) 计算 10日100% / 30日200% 偏离值 | 🚧 开发中 |
| **情绪/热度** | 外部爬虫 | 东方财富/同花顺热榜 (App Hot List) | 🚧 计划接入 |

---

## 📁 目录结构

* `src/core/`: 核心逻辑
    * `pool_generator_tushare.py`: **[主程序]** 每日复盘策略工厂 (V3.4)。
    * `filter.py`: 选股过滤器 (黑名单/市值/ST/持仓过滤)。
    * `stock_tagger.py`: 自动打标系统 (如 "3天2板", "反包", "龙虎榜净买")。
* `src/data/tushare_source/`: 数据接入层
    * `fetcher.py`: 负责聚合拉取日线、竞价、筹码等数据。
* `src/monitors/`: 监控终端
    * `call_auction_screener.py`: **[竞价]** 9:25-9:30 弱转强筛选。
    * `intraday_monitor.py`: **[盘中]** 实时持仓盯盘。
* `src/strategies/`: 策略库
    * `auction.py`: 竞价强弱判定算法。

---

## 🕒 每日作业流程 (Workflow)

### 1. 盘后复盘 (17:00 - 20:00)

目标：生成明日的 **策略池 (Strategy Pool)**。

1.  **准备数据**:
    * 无需手动导出同花顺数据（除非 Tushare 接口故障）。
    * 确保 `Config.HOLDINGS_PATH` (持仓) 和 `Config.F_LAO_PATH` (大佬作业) 已更新。

2.  **运行生成器**:
    ```bash
    python src/core/pool_generator_tushare.py
    ```
    * **执行逻辑**:
        1.  自动拉取当日行情、涨跌停数据。
        2.  拉取龙虎榜数据，标记知名游资入驻个股。
        3.  拉取筹码数据（需19:30后），标记获利盘比例。
        4.  **过滤器 (Filter)**: 剔除 ST、流动性差（成交额 < 5000万）的杂毛。
        5.  **打标 (Tagger)**: 识别“首板”、“连板”、“反包”等形态。
    * **输出**: `data/output/strategy_pool.csv`

### 2. 竞价筛选 (9:25 - 9:30)

目标：在开盘前 5 分钟锁定 **“弱转强”** 标的。

1.  **运行监控**:
    ```bash
    python src/monitors/call_auction_screener.py
    ```
2.  **核心看点**:
    * **🔥 弱转强**: 昨日烂板/断板/阴线 -> 今日**高开** + **爆量** (竞价额 > 昨日成交 5%-10%)。
    * **📉 核按钮**: 竞价跌幅 < -5%，提示风险（若持有需警惕，若未持有需规避）。
    * **💰 抢筹**: 竞价金额 > 1亿，说明主力意图强烈。

### 3. 盘中盯盘 (9:30 - 15:00)

1.  **运行监控**:
    ```bash
    python src/monitors/intraday_monitor.py
    ```
    * 实时监控持仓股的盈亏状况。
    * 监控策略池中触发 **“大单点火”** 或 **“快速拉升”** 的个股。

---

## 🧠 核心策略逻辑

### 1. 弱转强 (Weak to Strong)
* **定义**: 个股在经历了前一日的分歧（烂板、大阴线、炸板）后，次日竞价或开盘表现出一致性转强（高开、快速上攻）。
* **代码实现**: 见 `src/strategies/auction.py`
    * `analyze_status`: 判定 `yest_pct < 0` 且 `auc_pct > 0.5`。

### 2. 筹码支撑 (Chip Support) **[NEW]**
* **逻辑**: 股价回调至主力成本区（`cost_5pct`）或获利盘比例极低（`winner_rate` < 1%）时，往往有反弹需求。
* **应用**: 在 `fetcher.py` 中注入 `winner_rate`，辅助判断底部承接。

### 3. 监管风控 (Regulation Risk) **[Planned]**
* **关注**: 10日涨幅偏离值 > 100% 或 30日 > 200%。
* **操作**: 触及红线前禁止追高，主力往往会主动回调控制异动。

---

## 📝 配置说明

* `src/config/settings.py`: 修改 Tushare Token 和路径配置。
* `data/input/holdings.txt`: 你的持仓代码（每行一个）。
* `data/input/f_lao_list.txt`: 重点跟踪的代码池。