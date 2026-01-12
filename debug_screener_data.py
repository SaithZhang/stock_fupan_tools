
import os
import pandas as pd
import re

def analyze_file():
    # Find the file
    base_dir = r"d:\work\pyproject\data\input\call_auction"
    files = [f for f in os.listdir(base_dir) if f.endswith('.txt')]
    # Sort by mtime
    files.sort(key=lambda x: os.path.getmtime(os.path.join(base_dir, x)), reverse=True)
    
    if not files:
        print("No files found!")
        return
        
    target_file = files[0]
    path = os.path.join(base_dir, target_file)
    print(f"Analyzing: {target_file}")
    
    # 1. Inspect Raw Content
    print("\n[Raw Content First 3 lines]")
    try:
        with open(path, 'rb') as f:
            for i in range(3):
                print(f"L{i}: {f.readline()}")
    except Exception as e:
        print(f"Raw read error: {e}")

    # 2. Try Standard Parsing (Tab)
    print("\n[Attempt 1: sep='\\t']")
    try:
        df = pd.read_csv(path, sep='\t', encoding='utf-8', on_bad_lines='skip')
        print(f"Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print("First Row:", df.iloc[0].tolist() if not df.empty else "Empty")
        
        # Check standard columns
        for c in df.columns:
            if "竞价涨幅" in str(c): print(f"Found Pct Col: {c}")
    except Exception as e:
        print(f"Error: {e}")

    # 3. Try Regex Parsing (Whitespace)
    print("\n[Attempt 2: sep=r'\\s+']")
    try:
        df = pd.read_csv(path, sep=r'\s+', encoding='utf-8', on_bad_lines='skip')
        print(f"Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print("First Row:", df.iloc[0].values)
        
        for c in df.columns:
             if "竞价涨幅" in str(c): print(f"Found Pct Col: {c}")
             
        # Check value of 000901 if exists
        mask = df.iloc[:,0].astype(str).str.contains("000901")
        if mask.any():
            print("\nRow for 000901:")
            print(df[mask])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_file()
