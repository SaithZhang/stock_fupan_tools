# 股票复盘与监控系统 (Stock Review & Monitor System)

本工程用于日常股票复盘、策略筛选及盘中监控。主要包含数据导入、策略池生成、竞价/盘中监控等功能。

## 📁 目录结构

*   `src/core/`: 核心逻辑 (数据加载、策略池生成、复盘工具)
*   `src/monitors/`: 监控脚本 (竞价筛选、盘中监控)
*   `src/tools/`: 辅助工具 (数据爬取、测试脚本)
*   `data/input/`: 数据输入目录 (同花顺、开盘啦等导出文件)
*   `data/output/`: 策略结果输出

---

## 🕒 每日作业流程 (Workflow)

### 1. 盘后准备 (Post-Market)

每天收盘后或第二天开盘前，需要从软件导出数据并运行复盘脚本。

#### 步骤 A: 导出同花顺数据 (主要数据源)

请在同花顺中建立自定义表头，包含以下字段：
> 代码, 名称, 现价, 涨幅, 成交额, 换手, 连续涨停, 涨停原因, 几天几板, 10日涨幅, 竞价涨幅, 早盘竞价金额, 所属行业, 20日涨幅, 开板次数

*   **全市场数据 (Table)**: 导出全市场所有股票数据。
    *   **存放路径**: `data/input/ths/`
    *   **文件名**: `Table-YYYYMMDD.txt` (例如 `Table-20260112.txt`)

*   **大盘与板块数据 (可选但推荐)**:
    *   **大盘指数**: 导出主要指数数据 -> `data/input/ths/dapan-YYYYMMDD.txt`
    *   **行业/概念**: 导出行业和概念板块数据 -> `data/input/ths/industries/` 和 `data/input/ths/concepts/`

#### 步骤 B: 导出开盘啦数据 (异动/风险)

*   **异动数据**: 从开盘啦导出当日的异动/风险提示数据。
    *   **存放路径**: `data/input/risk/`
    *   **文件名**: `risk_YYYYMMDD.csv`
    *   **关键列**: `股票名称`, `监管规则`, `当前累计偏离值`, `风险等级`

#### 步骤 C: 运行龙虎榜 & 复盘生成

1.  **更新龙虎榜**:
    运行 `src/core/lhb_scanner.py` (会自动爬取并生成 `lhb_latest.csv`)。

2.  **生成策略池**:
    运行 **`src/core/pool_generator.py`**。
    *   **作用**: 读取上述导出的数据，结合持仓 (`holdings.txt`) 和关注列表 (`f_lao_list.txt`)，生成当日的策略池。
    *   **输出**: `data/output/strategy_pool.csv` (这是第二天监控的核心输入)。

---

### 2. 盘前/竞价 (9:15 - 9:30)

*   **运行脚本**: `src/monitors/call_auction_screener.py`
    *   **作用**: 监控竞价阶段的表现，筛选出符合策略（如高开、爆量等）的标的。
    *   **输入**: 依赖前一天生成的 `strategy_pool.csv`。

### 3. 盘中监控 (9:30 - 15:00)

*   **运行脚本**: `src/monitors/intraday_monitor.py`
    *   **作用**: 实时监控持仓股和策略池中的标的。
    *   **显示信息**: 实时价格、涨幅、大盘情绪、各种预警信号。

---

## 🛠️ 模块说明 (Modules)

| 模块 | 脚本名 | 说明 |
| :--- | :--- | :--- |
| **盘后生成** | `src/core/pool_generator.py` | **【核心】** 每日必跑。整合多方数据生成策略大表。 |
| **数据加载** | `src/core/data_loader.py` | 通用工具，负责解析同花顺、通达信等各种格式的数据文件。 |
| **龙虎榜** | `src/core/lhb_scanner.py` | 爬取并分析每日龙虎榜，识别游资动向。 |
| **竞价监控** | `src/monitors/call_auction_screener.py` | **9:25后运行**。分析竞价强弱，辅助开盘决策。 |
| **盘中监控** | `src/monitors/intraday_monitor.py` | **盘中常驻**。实时盯盘助手，监控大盘与个股异动。 |
| **NGA爬虫** | `src/tools/nga_scraper.py` | 抓取论坛大佬观点，辅助构建关注股票池。 |
| **同花顺导入**| `src/tools/import_ths_data.py` | 辅助脚本，有时用于测试数据导入逻辑。 |

## 📝 配置文件 (Data Input)

*   `data/input/holdings.txt`: **持仓列表**。每行一个代码，用于特别关注。
*   `data/input/f_lao_list.txt`: **大佬关注列表**。来源 NGA 或手动添加，作为重点筛选池。
*   `data/input/manual_focus.txt`: **手动核心关注**。用于添加一时兴起或特别看好的标的。
