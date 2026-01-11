
import os
import pandas as pd
import re
import glob
from datetime import datetime

# Define rules
# 1. 焚诀-趋势强: 连续3日放量收红 (Vol(t) > Vol(t-1) AND Pct > 0)
# 2. 焚诀-买点: 趋势强后，首日缩量阴线 (Vol(t) < Vol(t-1) AND Pct < 0) 且未破5日线(近似)
# 3. 断板反包: 昨日(T-1)炸板/断板，今日(T)放量收红

def load_ths_history(data_dir, days=5):
    """
    Load last N days of THS data.
    Returns: {code: [ {date, pct, vol, amount, price, name, is_zt, ...} ] sorted by date}
    """
    if not os.path.exists(data_dir):
        return {}
    
    # 1. Find all Table-YYYYMMDD.txt
    files = []
    for f in os.listdir(data_dir):
        if f.startswith("Table") and f.endswith(".txt"):
            match = re.search(r'(\d{8})', f)
            if match:
                files.append({'path': os.path.join(data_dir, f), 'date': match.group(1)})
    
    # Sort by date desc and take last N
    files.sort(key=lambda x: x['date'], reverse=True)
    target_files = files[:days]
    target_files.sort(key=lambda x: x['date']) # Sort ASC for processing
    
    history_map = {}
    
    for f_info in target_files:
        path = f_info['path']
        date_str = f_info['date']
        
        try:
            # Flexible reading for encoding/header
            df = None
            encodings = ['gbk', 'utf-8', 'utf-16']
            for enc in encodings:
                try:
                    df = pd.read_csv(path, sep=r'\t+', engine='python', encoding=enc, dtype=str)
                    if any('代码' in c for c in df.columns): break
                except:
                    continue
            
            if df is None: continue
            
            df.columns = [c.strip() for c in df.columns]
            
            # Identify columns
            col_code = next((c for c in df.columns if '代码' in c), None)
            col_pct = next((c for c in df.columns if '涨幅' in c and '竞价' not in c and '10' not in c), None)
            col_vol = next((c for c in df.columns if '成交量' in c or '现手' in c), None) # THS usually has '现手' for current vol, but history uses '成交量' or just derive from amount? 
            # Table.txt usually has '成交额'. Let's use Amount as proxy for Volume if Volume missing, or try find '现手'
            col_amt = next((c for c in df.columns if '成交额' in c), None)
            col_price = next((c for c in df.columns if '现价' in c), None)
            col_zt = next((c for c in df.columns if '涨停' in c or '连板' in c), None)
            col_name = next((c for c in df.columns if '名称' in c), None)
            
            for _, row in df.iterrows():
                try:
                    code = str(row[col_code]).strip()
                    code = re.sub(r'\D', '', code)
                    if len(code) != 6: continue
                    
                    pct = float(row.get(col_pct, 0)) if col_pct else 0.0
                    amt = float(row.get(col_amt, 0)) if col_amt else 0.0
                    price = float(row.get(col_price, 0)) if col_price else 0.0
                    name = str(row.get(col_name, ''))
                    
                    # Clean Amt/Vol
                    # Usually in data_loader we handle '万/亿', here assume simple parse or re-use logic
                    # Simplification: THS export usually raw numbers or consistent. 
                    # If strings with units, need parsing. Let's assume raw or simple.
                    # Wait, data_loader uses safe_float. Let's define simple safe_float here.
                    
                    if code not in history_map: history_map[code] = []
                    
                    history_map[code].append({
                        'date': date_str,
                        'pct': pct,
                        'amount': amt, # Use amount as primary volume indicator for 'Fen Jue' (funds flow)
                        'price': price,
                        'name': name,
                        'is_zt': (pct > 9.8) or (str(row.get(col_zt, '')) not in ['--', '', 'nan'])
                    })
                except:
                    continue
        except Exception as e:
            print(f"Error loading {path}: {e}")
            
    return history_map

def check_fen_jue(history_list):
    """
    Analyze standard 'Fen Jue' status.
    history_list: sorted list of daily data. Last element is Today (or Latest).
    """
    if len(history_list) < 3:
        return []
    
    tags = []
    
    today = history_list[-1]
    yest = history_list[-2]
    day3 = history_list[-3]
    
    # Stats
    vol_t = today['amount']
    vol_y = yest['amount']
    pct_t = today['pct']
    pct_y = yest['pct']
    
    # 1. 连续放量阳线 (Continuous Volume Red)
    # Check last 3 days: Vol increasing, Pct > 0
    # Loose criteria: Last 2 days strong increase, or 3 days steady
    is_trend_up = False
    if vol_t > vol_y and pct_t > 0 and vol_y > day3['amount'] and pct_y > 0:
        is_trend_up = True
    
    if is_trend_up:
        # Check if today is ZT
        if today['is_zt']:
            tags.append("🔥焚诀/加速")
        else:
            tags.append("🔥焚诀/趋势")
            
    # 2. 焚诀买点 (Shrinking Vol, Green/Small Red, Trend was Up)
    # Means Yesterday was part of Up Trend, Today is correction
    # Check Yesterday's Trend
    trend_yest = (vol_y > day3['amount'] and pct_y > 0) or (yest['is_zt'])
    
    if trend_yest:
        # Today condition: Shrinking Volume AND (Green OR Small Red < 3%)
        if vol_t < vol_y:
            if pct_t < 0 or (pct_t < 3.0 and not today['is_zt']):
                tags.append("👀焚诀/分歧低吸")
                
    # 3. A大焚诀 (A-Da Fen Jue) - 断板次日收红
    # Logic: 
    #   T-2 was Limit Up (is_zt=True)
    #   T-1 was Broken (is_zt=False)
    #   T is Up (pct > 0)
    #   Optional: Vol T > Vol T-1 (Explosive Volume preferential)
    
    is_duanban = False
    # Condition: T-2 was ZT, T-1 was NOT ZT
    if day3['is_zt'] and not yest['is_zt']:
        is_duanban = True
        
    # Also consider "Zhaban" yesterday (touched limit up but failed)
    # We might not detect "touched" easily without high/max_pct, but usually user implies 'Broken Streak' or 'Failed Board'
    # If the user emphasizes "Yesterday Broken Board", T-2 ZT -> T-1 No ZT is the clearest signal of a streak break.
    
    if is_duanban:
        if pct_t > 0:
            label = "🔥A大焚诀"
            # Add volume info
            if vol_t > vol_y:
                 label += "/爆量"
            else:
                 label += "/缩量"
            tags.append(label)

    return tags

def safe_float(val):
    if pd.isna(val) or val == '--' or val == '': return 0.0
    s = str(val).strip()
    try:
        return float(s)
    except:
        return 0.0



if __name__ == "__main__":
    # Test
    # Assume we run from project root
    ths_dir = os.path.join("data", "input", "ths")
    hist_map = load_ths_history(ths_dir)
    print(f"Loaded {len(hist_map)} stocks history")
    
    # Test a few
    for code, h_list in list(hist_map.items())[:5]:
        print(f"{code}: {len(h_list)} days")
        tags = check_fen_jue(h_list)
        if tags: print(f"  Tags: {tags}")
