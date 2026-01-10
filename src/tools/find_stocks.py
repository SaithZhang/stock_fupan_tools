import os

def find_stocks():
    # Keep absolute path or make it dynamic if needed
    # Assuming the file structure stays somewhat consistent on this machine
    table_path = r'd:\work\pyproject\data\input\ths\Table-20260108.txt'
    
    target_names = [
        '巨力', '张江', '海格', '金风', '顺灏', '通宇', 
        '利欧', '南兴', '锋龙', '巨轮', '万向', '五洲', '泰尔', 
        '创新', '熊猫', '岩山', '普利特', '安记', '上海九百', 
        '一重', '核建', '塞力'
    ]
    
    found = {}
    
    try:
        with open(table_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(table_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except:
             print("Failed to read file with utf-8 or gbk")
             return

    print(f"Searching {len(target_names)} names in {len(lines)} lines...")

    for line in lines:
        parts = line.split('\t')
        if len(parts) < 2: 
            parts = line.split() # Try space split
        
        if len(parts) >= 2:
            code = parts[0].strip()
            name = parts[1].strip()
            
            # Remove SH/SZ for clean code
            clean_code = code.replace('SH', '').replace('SZ', '')
            if not clean_code.isdigit(): continue

            for t in target_names:
                if t in name:
                    # Special handling for ambiguous matches if needed
                    # But usually first match is okay.
                    # We store all matches for manual selection if needed
                    if t not in found: found[t] = []
                    found[t].append((clean_code, name))

    for t in target_names:
        if t in found:
            for code, name in found[t]:
                print(f"Match: {t} -> {code} ({name})")
        else:
            print(f"Match: {t} -> NOT FOUND")

if __name__ == '__main__':
    find_stocks()
