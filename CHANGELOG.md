# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-01-11

### Added
- **Market Data Integration**: 
    - Created `src/core/market_data.py` compliant with `MarketDataManager` class.
    - Implemented robust loading for THS export files (Indices, Industries, Concepts).
    - Added parsing for Market Breadth (Rise/Fall counts) and Sector Net Inflows.
- **Strategy Pool Enhancement**:
    - Updated `pool_generator.py` to utilize `MarketDataManager`.
    - `market_sentiment.json` now includes consolidated turnovers, sector ranks, and sentiment indicators.
    - `strategy_pool.csv` generation logic verified for weekend consistency.
- **Unit Testing Framework**:
    - Initialized `tests/` directory.
    - Added `pytest` dependency.
    - Created `tests/test_market_data.py` for data integrity checks.
    - Created `tests/test_date_logic.py` to verify weekend/holiday file selection logic.
    - Added `run_tests.py` helper script.

### Changed
- Refactored `call_auction_screener.py` to seamlessly use the new `strategy_pool.csv` tags.
- Improved CSV parsing robustness in data loaders (handling mixed delimiters and malformed lines).

### Fixed
- Fixed potential weekend data loading issue by strictly using file dates instead of system time.
