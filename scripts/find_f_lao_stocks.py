import sys
import os
import re

# Add path to src
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(os.path.join(project_root, 'src', 'core'))
sys.path.append(project_root)

try:
    from src.core.data_loader import get_merged_data
except ImportError:
    # Quick mock if import fails (shouldn't happen in this env)
    pass

def match_stocks():
    print("Loading all stock data...")
    all_data = get_merged_data()
    name_map = {item['name']: item['code'] for item in all_data}
    
    # User text processed into keywords
    text = """
    张江 利欧 创元 万向 大为 航天晨光 华菱线缆 远东股份 
    中水 孚日 国风 华瓷 
    雷科 电子 华菱 晨光 
    天奇 山子 五洲 
    金风
    """
    # Split by spaces and newlines
    keywords = re.split(r'\s+', text.strip())
    keywords = [k for k in keywords if len(k) >= 2] # Filter out single chars or empty
    
    exact_matches = []
    fuzzy_matches = []
    
    print(f"Keywords: {keywords}")
    
    for k in keywords:
        found = False
        # 1. Exact match
        if k in name_map:
            exact_matches.append((k, name_map[k]))
            found = True
        else:
            # 2. Contains match (taking the shortest Name that contains keyword)
            candidates = [n for n in name_map.keys() if k in n]
            if candidates:
                # Sort by length (shorter usually implies closer match, e.g. "张江" -> "张江高科" vs "张江xxx")
                candidates.sort(key=len)
                best = candidates[0]
                fuzzy_matches.append((k, best, name_map[best]))
                found = True
        
        if not found:
            print(f"⚠️ No match for: {k}")

    print("\n--- Matches Found ---")
    for k, name, code in fuzzy_matches:
        print(f"{clean_code(code)} {name}  # from '{k}'")
    for name, code in exact_matches:
        print(f"{clean_code(code)} {name}")

def clean_code(c):
    return str(c).split('.')[0]

if __name__ == "__main__":
    match_stocks()
