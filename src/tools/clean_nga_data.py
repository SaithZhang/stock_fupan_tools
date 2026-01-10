import pandas as pd
import os

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "output", "f_lao_reviews_v2.csv")

def clean_data():
    if not os.path.exists(OUTPUT_FILE):
        print("File not found.")
        return

    print(f"Reading {OUTPUT_FILE}...")
    try:
        df = pd.read_csv(OUTPUT_FILE)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return
        
    original_count = len(df)
    print(f"Original row count: {original_count}")
    
    # Drop duplicates
    # Consider Date and Content as unique keys
    df_clean = df.drop_duplicates(subset=['date', 'content'])
    
    # Sort by date
    try:
        df_clean['date'] = pd.to_datetime(df_clean['date'], format='mixed', dayfirst=False, errors='coerce')
        df_clean = df_clean.sort_values(by='date')
    except:
        pass
        
    new_count = len(df_clean)
    print(f"Cleaned row count: {new_count}")
    print(f"Removed {original_count - new_count} duplicates.")
    
    df_clean.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
    print("Saved cleaned file.")

if __name__ == "__main__":
    clean_data()
