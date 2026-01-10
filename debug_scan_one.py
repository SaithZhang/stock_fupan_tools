import akshare as ak
import pandas as pd

FAMOUS_SEATS = {
    '陈小群': [
        '大连金马路', '中国银河证券股份有限公司大连金马路',
        '大连黄河路', '中国银河证券股份有限公司大连黄河路',
        '苏州留园路', '东亚前海证券有限责任公司苏州留园路'
    ]
}

def debug_one():
    code = "002202"
    date_str = "20260108"
    print(f"Checking {code}...")
    
    try:
        df = ak.stock_lhb_stock_detail_em(symbol=code, date=date_str)
        if df.empty:
            print("Empty df")
            return
            
        print("Columns:", df.columns.tolist())
        
        for i, row in df.iterrows():
            branch = str(row.get('营业部名称') or row.get('交易营业部名称', ''))
            buy = row.get('买入金额', 0)
            sell = row.get('卖出金额', 0)
            print(f"Row {i}: {branch} | Buy: {buy} | Sell: {sell}")
            
            for label, keywords in FAMOUS_SEATS.items():
                for kw in keywords:
                    if kw in branch:
                        print(f"  MATCH: {label} (kw: {kw})")
                        
    except Exception as e:
        print(e)
        
if __name__ == "__main__":
    debug_one()
