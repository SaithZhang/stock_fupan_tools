# Changelog

All notable changes to the **Stock Fupan Tools** project will be documented in this file.

## [1.2.0] - 2026-01-04
### Added
- **Structure**: 项目结构重构，分离策略、监控与核心逻辑。
- **Monitors**: 集成 F佬监管与拨佬竞价逻辑 (`auction_watch.py`)。
- **Strategies**: 新增逆势猎手 (`divergence.py`) 与 监管异动计算 (`regulatory_risk.py`)。
- **Core**: 路径增强版生成器，支持项目根目录自动寻址。

### Changed
- 优化了同花顺剪贴板 (`ths_clipboard.txt`) 的解析逻辑，兼容 GBK/UTF-8 编码。
- 优化了控制台输出样式，引入 `colorama` 实现红绿高亮。
- 移除了旧版 `get_auctio.py` 等冗余脚本。

## [1.0.0] - Initial
- 基础复盘工具集。