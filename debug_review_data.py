import akshare as ak
import pandas as pd

def test_index_min():
    print("\n--- Testing Index Minute Data ---")
    # Try 1: stock_zh_a_hist_min_em with sh000001 - usually for stocks but some backends mix them.
    try:
        print("Try 1: stock_zh_a_hist_min_em('sh000001')")
        df = ak.stock_zh_a_hist_min_em(symbol="sh000001", period="1", adjust="qfq")
        print(f"Result: {len(df)} rows")
        print(df.tail(2))
        return
    except Exception as e:
        print(f"Failed: {e}")

    # Try 2: specific index function
    try:
        print("Try 2: index_zh_a_hist_min_em('sh000001')")
        # Checking if this exists
        if hasattr(ak, 'index_zh_a_hist_min_em'):
             df = ak.index_zh_a_hist_min_em(symbol="sh000001", period="1")
             print(f"Result: {len(df)} rows")
             print(df.tail(2))
             return
        else:
             print("Function does not exist")
    except Exception as e:
        print(f"Failed: {e}")
        
    # Try 3: stock_zh_a_hist_min_em with just "000001" (might be PingAn, need to check name)
    # PingAn is 000001, Index is sh000001. 
    # Try 4: "1.000001" (EastMoney style for SH index)
    try:
        print("Try 4: stock_zh_a_hist_min_em('1.000001') style?")
        # Usually akshare handles symbol conversion.
        pass
    except:
        pass

def main():
    test_index_min()

if __name__ == "__main__":
    main()
