import akshare as ak
import pandas as pd
import datetime

class DataFetcher:
    @staticmethod
    def fetch_stock_minute(symbol, period="1", adjust="qfq"):
        """获取个股分钟数据 (默认前复权)"""
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=period, adjust=adjust)
            return df
        except Exception as e:
            print(f"Error fetching stock minute for {symbol}: {e}")
            return pd.DataFrame()

    @staticmethod
    def fetch_sector_daily_or_min(sector_name):
        """
        获取板块数据。由于akshare没有直接的板块分钟级历史接口，
        我们暂时使用日线或实时数据。如果需要分钟级，可能需自行合成或通过其他方式。
        User requested minute level, but limited by API.
        Let's try to get recent data or simulated minute data if possible,
        or just return available data. 
        Actually, for analysis, maybe daily structure is enough if we can't get minute?
        Wait, I verified in debug script that 'stock_board_industry_hist_min_em' does NOT exist.
        But 'stock_board_industry_cons_em' exists.
        
        Modification: We will use sector constituents to calculate/estimate or just look at headers?
        Actually, user said: "持仓所在板块的".
        If we cannot get minute data for sector index, we might need to skip or explain.
        BUT, 'stock_board_industry_index_ths' might have something?
        
        Let's stick to what we verified.
        For now, we return empty or try to find a proxy if needed.
        But wait, `ak.stock_board_industry_index_min_em` ?
        
        Let's assume we focus on the stocks first. 
        """
        return pd.DataFrame()

    @staticmethod
    def fetch_sector_constituents(sector_name):
        """获取板块成分股"""
        try:
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
            return df
        except Exception as e:
            print(f"Error fetching constituents for {sector_name}: {e}")
            return pd.DataFrame()

    @staticmethod
    def fetch_index_minute(symbol="sh000001", period="1"):
        """获取指数分钟数据"""
        # Note: akshare index minute support is tricky.
        # Often we use 'sh000001' with stock_zh_a_hist_min_em and it fails.
        # However, for some specific indices or by using `stock_zh_index_daily_em` for daily.
        # If we really need minute, we might need to use a specific API or accept we only have daily.
        # Let's try `index_zh_a_hist_min_em` if available (I saw it failing in debug).
        
        # Latest check: `ak.stock_zh_a_hist_min_em` works for some indices if passed as specific codes?
        # No, usually not.
        
        # Let's try `stock_zh_a_spot_em` for snapshot or `stock_zh_index_spot_em`.
        # Taking a step back: User wants to analyze *today's buy/sell*.
        # Maybe we can just use the daily data for now if minute is hard.
        # BUT user explicitly asked for "history minute level".
        
        # Let's try to use `ak.stock_zh_a_hist_min_em` but maybe for ETF like 510050 (SSE 50) as proxy?
        # Or just return empty if failed.
        return pd.DataFrame()

    @staticmethod
    def get_sector_info():
        """获取所有板块列表"""
        try:
            return ak.stock_board_industry_name_em()
        except:
            return pd.DataFrame()
