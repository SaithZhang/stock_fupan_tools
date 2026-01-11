import os
import pandas as pd
import json

class MarketDataManager:
    def __init__(self, input_dir):
        self.input_dir = input_dir
        self.data = None
        self.calculated = {}
        self.file_loaded = None
        
    def find_latest_file(self):
        """Find the latest dapan-YYYYMMDD.txt file"""
        if not os.path.exists(self.input_dir):
            return None
        
        files = [f for f in os.listdir(self.input_dir) if f.startswith('dapan-') and f.endswith('.txt')]
        if not files:
            return None
            
        # Sort by date in filename: dapan-20260109.txt
        files.sort(reverse=True)
        return os.path.join(self.input_dir, files[0])

    def find_latest_file_in_dir(self, sub_dir, prefix):
        """Find latest file in specific subdirectory"""
        target_dir = os.path.join(self.input_dir, "..", "ths", sub_dir)
        # Fallback if self.input_dir is pointing to 'data/input/dapan'
        # We need 'data/input/ths/sub_dir'
        
        # Check if we are relatively close
        if not os.path.exists(target_dir):
             # Try absolute resolution based on project root assumption
             # self.input_dir usually is .../data/input/dapan
             # We want .../data/input/ths
             parent = os.path.dirname(self.input_dir)
             target_dir = os.path.join(parent, "ths", sub_dir)
             
        if not os.path.exists(target_dir):
            return None
            
        files = [f for f in os.listdir(target_dir) if f.startswith(prefix) and f.endswith('.txt')]
        if not files:
            return None
            
        # Sort by date usually embedded in filename
        files.sort(reverse=True)
        return os.path.join(target_dir, files[0])

    def load_data(self):
        """Load and parse all market data files"""
        # 1. Main Index (Dapan)
        filepath = self.find_latest_file()
        if filepath:
            try:
                # Parse using whitespace as delimiter
                df = pd.read_csv(filepath, sep=r'\s+', engine='python', encoding='utf-8', dtype=str, on_bad_lines='skip')
                df.columns = [c.strip() for c in df.columns]
                df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
                
                # Ensure '代码' is stripped
                if '代码' in df.columns:
                    df['代码'] = df['代码'].str.strip()
                
                self.data = df
                self._calculate_metrics()
            except Exception as e:
                print(f"❌ MarketDataManager: Error loading main index {filepath}: {e}")
        
        # 2. Broad Indices (Breadth)
        idx_path = self.find_latest_file_in_dir("indices", "indices")
        if idx_path:
            self._parse_breadth(idx_path)
            
        # 3. Sectors (Industries)
        ind_path = self.find_latest_file_in_dir("industries", "industry")
        if ind_path:
            self._parse_sectors(ind_path, "industry")
            
        # 4. Concepts
        con_path = self.find_latest_file_in_dir("concepts", "concept")
        if con_path:
            self._parse_sectors(con_path, "concept")
            
        return True # Return true if at least something loaded (or tried)

    def _parse_breadth(self, filepath):
        try:
            df = pd.read_csv(filepath, sep=r'\s+', engine='python', encoding='utf-8', dtype=str, on_bad_lines='skip')
            # COLS: 板块名称 涨幅 ... 涨家数 跌家数
            # Find "同花顺全A(沪深)" or similar
            row = df[df['板块名称'].str.contains("同花顺全A")].iloc[0] if not df.empty else None
            
            if row is not None:
                # Parse Rise/Fall
                rise = int(row.get('涨家数', 0))
                fall = int(row.get('跌家数', 0))
                total = rise + fall
                
                # Sentiment Score (Simple)
                sentiment_msg = "😐震荡"
                if rise > 3500: sentiment_msg = "🔥普涨"
                elif rise > 2500: sentiment_msg = "🙂多头"
                elif fall > 3500: sentiment_msg = "❄️普跌"
                elif fall > 2500: sentiment_msg = "🤢空头"
                
                if self.calculated is None: self.calculated = {}
                self.calculated['market_breadth'] = {
                    'rise_count': rise,
                    'fall_count': fall,
                    'sentiment': sentiment_msg
                }
        except Exception as e:
            print(f"⚠️ Breadth parse failed: {e}")

    def _parse_sectors(self, filepath, type_key):
        try:
            df = pd.read_csv(filepath, sep=r'\s+', engine='python', encoding='utf-8', dtype=str, on_bad_lines='skip')
            # Need: Name, Pct, Amount(主力净量/主力金额? Users usually care about Net Inflow)
            # File has "主力净量"(Net Ratio?) and "主力金额"(Net Amount)
            
            def clean_float(x):
                if isinstance(x, str):
                    x = x.replace('%', '').replace('+', '')
                    if x == '--': return 0.0
                return float(x)
            
            sectors = []
            for _, row in df.iterrows():
                name = row['板块名称']
                pct = clean_float(row['涨幅'])
                net_amt = clean_float(row.get('主力金额', 0))
                
                sectors.append({
                    'name': name,
                    'pct': pct,
                    'net_inflow': net_amt
                })
                
            # Top Gainers
            sectors.sort(key=lambda x: x['pct'], reverse=True)
            top_gainers = sectors[:5]
            
            # Top Inflows
            sectors.sort(key=lambda x: x['net_inflow'], reverse=True)
            top_inflows = sectors[:5]
            
            if self.calculated is None: self.calculated = {}
            if 'sector_ranks' not in self.calculated: self.calculated['sector_ranks'] = {}
            
            self.calculated['sector_ranks'][type_key] = {
                'gainers': top_gainers,
                'inflows': top_inflows
            }
            
        except Exception as e:
            print(f"⚠️ Sector parse failed ({type_key}): {e}")

    def _calculate_metrics(self):
        if self.data is None or self.data.empty:
            return

        # Indices of interest
        # SH000001: 上证指数
        # SZ399001: 深证成指
        # SZ399006: 创业板指
        # SH000688: 科创50
        # SH000300: 沪深300
        # SZ399303: 国证2000 (Proxy for small caps)
        
        def parse_amount(s):
            # Format: 1289205970000 (Bytes/Raw) -> need float
            if isinstance(s, str):
                s = s.strip()
            if not s or s == '--' or s == 'nan': return 0.0
            try:
                return float(s)
            except:
                return 0.0
            
        def parse_pct(s):
            # Format: +0.92% -> 0.92
            if isinstance(s, str):
                s = s.strip()
            if not s or s == '--' or s == 'nan': return 0.0
            try:
                return float(s.replace('%', '').replace('+', ''))
            except:
                return 0.0

        def get_row(code):
            # Look for Exact Match first
            row = self.data[self.data['代码'] == code]
            if not row.empty:
                return row.iloc[0]
            # Try fuzzy if needed (though codes should be exact in export)
            return None

        # 1. Total Turnover (SH + SZ)
        sh_row = get_row('SH000001')
        sz_row = get_row('SZ399001')
        
        sh_amt = parse_amount(sh_row['总金额']) if sh_row is not None else 0.0
        sz_amt = parse_amount(sz_row['总金额']) if sz_row is not None else 0.0
        
        total_turnover = sh_amt + sz_amt
        
        # 2. Key Indices
        indices = {
            'sh_index': 'SH000001',
            'sz_index': 'SZ399001',
            'cyb_index': 'SZ399006',
            'kc50_index': 'SH000688',
            'gz2000_index': 'SZ399303' # Small cap proxy
        }
        
        index_data = {}
        for key, code in indices.items():
            row = get_row(code)
            if row is not None:
                index_data[key] = {
                    'name': row['名称'],
                    'pct': parse_pct(row.get('涨幅')),
                    'amount': parse_amount(row.get('总金额')),
                    'vol_ratio': parse_pct(row.get('量比', '0')) # Volume Ratio usually standard float, but let's check parsing
                }
            else:
                 index_data[key] = None

        if self.calculated is None: self.calculated = {}
        
        self.calculated.update({
            'date': getattr(self, 'file_loaded', '').split('dapan-')[-1].replace('.txt', ''),
            'total_turnover': total_turnover,
            'indices': index_data,
            'note': "Turnover is SH000001 + SZ399001"
        })

    def update_extra_stats(self, stats):
        """Update calculated stats with external data (e.g. sentiment, sectors)"""
        if self.calculated is None: self.calculated = {}
        self.calculated.update(stats)

    def get_summary(self):
        return self.calculated
        
    def get_formatted_summary(self):
        """Return a human-readable string summary"""
        c = self.calculated
        if not c:
            return "No market data available."
            
        turnover_yi = c.get('total_turnover', 0) / 100000000.0
        turnover_str = f"{turnover_yi:.0f}亿"
        if turnover_yi > 10000:
            turnover_str = f"{turnover_yi/10000:.2f}万亿"
            
        idx = c.get('indices', {})
        sh = idx.get('sh_index')
        sz = idx.get('sz_index')
        gz = idx.get('gz2000_index')
        
        sh_str = f"上证{sh['pct']:+.2f}%" if sh else ""
        sz_str = f"深成{sz['pct']:+.2f}%" if sz else ""
        gz_str = f"国证2000{gz['pct']:+.2f}%" if gz else ""
        
        # Breadth info
        breadth = c.get('market_breadth')
        breadth_str = ""
        if breadth:
            breadth_str = f" | {breadth['sentiment']} (⬆{breadth['rise_count']} ⬇{breadth['fall_count']})"
        
        return f"大盘: {turnover_str} | {sh_str} {sz_str} {gz_str}{breadth_str}"

if __name__ == "__main__":
    # Test run
    # Assuming run from project root
    base_dir = os.path.join(os.getcwd(), 'data', 'input', 'dapan')
    # If testing from src/core, adjust
    if not os.path.exists(base_dir):
        # try relative to script
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'input', 'dapan')
        
    md = MarketDataManager(base_dir)
    if md.load_data():
        print(md.get_formatted_summary())
        print(json.dumps(md.get_summary(), indent=2, ensure_ascii=False))
