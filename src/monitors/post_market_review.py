import os
import sys
import pandas as pd
import datetime
from colorama import init, Fore, Style

# Add project root to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

from src.utils.data_loader import load_holdings
from src.tools.data_fetcher import DataFetcher

init(autoreset=True)

def identify_sector(code, name):
    """
    Identify the sector of a stock.
    Since one stock might belong to multiple sectors, we try to find the 'main' or most active one.
    For simplicity, we can fetch all sectors for the stock and pick the first one 
    or the one with highest current heat if possible.
    
    LIMITATION: akshare's `stock_board_industry_name_em` lists all sectors.
    We need to find which sector this stock belongs to.
    Optimized approach: Get all industry cons once or just query specific stock sector?
    `ak.stock_individual_info_em(symbol=code)` might give industry.
    Let's try a simple approach: 
    We iterate through major industries? No, that's too slow.
    Eastmoney has `stock_board_industry_cons_em` but no reverse lookup easily.
    
    Alternative: `ak.stock_individual_info_em` returns '行业'.
    """
    try:
        # stock_individual_info_em is slow if called for many stocks.
        # But for holdings (usually < 10), it's fine.
        info = DataFetcher.fetch_stock_minute(code, period='1') # Just testing connectivity? No.
        
        # We need a proper function to get individual info
        # Let's add this to DataFetcher or just call ak here.
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        # df is usually: item, value
        industry = df[df['item'] == '行业']['value'].values[0]
        return industry
    except Exception as e:
        # print(f"Failed to identify sector for {code}: {e}")
        return None

def get_sector_leaders(sector_name):
    """
    Get 'High Standard' (Top Gainer) and 'Mid Army' (Top Turnover) for the sector.
    """
    try:
        cons = DataFetcher.fetch_sector_constituents(sector_name)
        if cons.empty: return None, None
        
        # Clean numeric columns
        cons['涨跌幅'] = pd.to_numeric(cons['涨跌幅'], errors='coerce')
        cons['成交额'] = pd.to_numeric(cons['成交额'], errors='coerce')
        
        # High Standard: Top Gainer
        cons_sorted_pct = cons.sort_values(by='涨跌幅', ascending=False)
        high_standard = cons_sorted_pct.iloc[0]
        
        # Mid Army: Top Turnover
        cons_sorted_amt = cons.sort_values(by='成交额', ascending=False)
        mid_army = cons_sorted_amt.iloc[0]
        
        return high_standard, mid_army
    except Exception as e:
        print(f"Error getting leaders for {sector_name}: {e}")
        return None, None

def save_for_ai(data_map, date_str):
    """
    Save the collected data into a text file for AI analysis.
    data_map: { code: { 'name':..., 'is_hold':..., 'sector':..., 'type':..., 'minute_data': df } }
    """
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'output', 'review')
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f'review_data_{date_str}.txt')
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"DATE: {date_str}\n")
        f.write("PURPOSE: Post-market review of holdings, comparing with sector leaders and index.\n")
        f.write("="*50 + "\n\n")
        
        # 1. Index Data
        idx_data = data_map.get('sh000001')
        if idx_data:
            f.write(f"INDEX: 上证指数 (sh000001)\n")
            f.write(idx_data['minute_data'].to_csv(index=False))
            f.write("\n" + "="*50 + "\n\n")
            
        # 2. Holdings and their context
        for code, info in data_map.items():
            if code == 'sh000001': continue
            if not info.get('is_hold'): continue
            
            f.write(f"HOLDING: {info['name']} ({code}) | Sector: {info.get('sector', 'N/A')}\n")
            f.write(f"COST: {info.get('cost', 0)}\n")
            f.write("MINUTE DATA:\n")
            f.write(info['minute_data'].to_csv(index=False))
            f.write("\n")
            
            # Associated Sector Leaders
            sector = info.get('sector')
            if sector:
                # High Standard
                hs_code = info.get('hs_code')
                if hs_code and hs_code in data_map:
                    hs_info = data_map[hs_code]
                    f.write(f"SECTOR HIGH STANDARD: {hs_info['name']} ({hs_code})\n")
                    f.write(hs_info['minute_data'].to_csv(index=False))
                    f.write("\n")
                
                # Mid Army
                ma_code = info.get('ma_code')
                if ma_code and ma_code in data_map:
                    ma_info = data_map[ma_code]
                    f.write(f"SECTOR MID ARMY: {ma_info['name']} ({ma_code})\n")
                    f.write(ma_info['minute_data'].to_csv(index=False))
                    f.write("\n")
            
            f.write("-" * 50 + "\n\n")

    print(f"\n✅ Data saved to: {filename}")
    return filename

def main():
    print(f"{Fore.CYAN}--- Post-Market Review Data Collector ---{Style.RESET_ALL}")
    
    # 1. Load Holdings
    holdings = load_holdings()
    if not holdings:
        print("No holdings found.")
        return

    print(f"Found {len(holdings)} holdings.")
    
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    data_map = {} # Store all collected info
    
    # 2. Fetch Index Data
    print("Fetching Index Data...")
    idx_df = DataFetcher.fetch_index_minute('sh000001') # Try sh000001 anyway
    # If empty, maybe try proxy or just skip
    if idx_df.empty:
         # Try 000001 (PingAn) just to see? No. 
         # Try to find a way to get index. 
         # For now, if empty, we just have empty index data.
         print("Warning: Index minute data empty.")
    
    data_map['sh000001'] = {
        'name': '上证指数',
        'type': 'INDEX',
        'minute_data': idx_df
    }
    
    # 3. Process Holdings
    for code, h_data in holdings.items():
        print(f"Processing holding: {code} ...")
        
        # A. Basic Info & Minute Data
        try:
             # We assume we can get name from recent history or just fetch
             # We need name for display. 
             # Let's simple fetch minute data, it usually doesn't have name in columns.
             # We can get name from sector cons or individual info.
             sector = identify_sector(code, "Unknown")
             
             min_df = DataFetcher.fetch_stock_minute(code)
             
             # Store Holding Info
             data_map[code] = {
                 'name': code, # Placeholder, maybe improved later
                 'is_hold': True,
                 'cost': h_data['cost'],
                 'sector': sector,
                 'minute_data': min_df,
                 'type': 'HOLDING'
             }
             
             if sector:
                 print(f"  > Sector: {sector}")
                 # B. Identify Sector Leaders
                 hs, ma = get_sector_leaders(sector)
                 
                 hs_code = str(hs['代码']).zfill(6) if hs is not None else None
                 ma_code = str(ma['代码']).zfill(6) if ma is not None else None
                 
                 data_map[code]['hs_code'] = hs_code
                 data_map[code]['ma_code'] = ma_code
                 
                 # C. Fetch Leader Data (if not already fetched)
                 if hs_code and hs_code not in data_map:
                     print(f"  > High Standard: {hs['名称']} ({hs_code})")
                     hs_df = DataFetcher.fetch_stock_minute(hs_code)
                     data_map[hs_code] = {
                         'name': hs['名称'],
                         'is_hold': False,
                         'sector': sector,
                         'minute_data': hs_df,
                         'type': 'HIGH_STANDARD'
                     }
                     
                 if ma_code and ma_code not in data_map:
                     print(f"  > Mid Army: {ma['名称']} ({ma_code})")
                     ma_df = DataFetcher.fetch_stock_minute(ma_code)
                     data_map[ma_code] = {
                         'name': ma['名称'],
                         'is_hold': False,
                         'sector': sector,
                         'minute_data': ma_df,
                         'type': 'MID_ARMY'
                     }
                     
        except Exception as e:
            print(f"Error processing {code}: {e}")
            
    # 4. Save
    save_for_ai(data_map, timestamp)

if __name__ == "__main__":
    main()
