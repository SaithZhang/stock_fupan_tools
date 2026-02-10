# src/data/tushare_source/fetcher.py
from src.data.tushare_source.pipeline import StockDataPipeline
from src.data.tushare_source.global_data import MarketOverview


class TushareFetcher:
    """
    🦅 [数据层门面]
    外部 (pool_generator) 只跟这个类交互，不需要知道内部是 pipeline 还是 global。
    """

    def __init__(self):
        # 1. 股票流水线
        self.stocks = StockDataPipeline()

        # 2. 市场全景数据
        self.market = MarketOverview()

    # 如果您想保持旧接口兼容，可以在这里做转发
    # 但建议直接在外部调用 self.stocks.run() 和 self.market.fetch_index()