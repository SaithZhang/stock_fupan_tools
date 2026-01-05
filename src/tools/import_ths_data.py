# ==============================================================================
# 🛠️ 本地数据导入器 (src/tools/import_ths_data.py) - v3.1 自动扫描版
# ==============================================================================
import pandas as pd
import json
import os
import re
import glob
from colorama import init, Fore

init(autoreset=True)

# ================= ⚙️ 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
INPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'input')
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'db', 'stock_concepts.json')

# 垃圾概念黑名单
BLACKLIST = [
    "融资融券", "深股通", "沪股通", "标准普尔", "富时罗素", "MSCI",
    "标普道琼斯", "证金持股", "转融券", "央视财经50", "同花顺漂亮100",
    "深成500", "上证380", "中证500", "创业板综", "机构重仓", "AH股",
    "基金重仓", "社保重仓"
]


def clean_concepts(concept_str):
    if not isinstance(concept_str, str): return ""
    concept_str = concept_str.replace("【", "").replace("】", "")
    parts = re.split(r'[;；\s]+', concept_str)
    valid_parts = []
    for p in parts:
        p = p.strip()
        if not p: continue
        if any(b == p for b in BLACKLIST): continue
        valid_parts.append(p)
    return "/".join(valid_parts[:8])  # 取前8个


def find_latest_data_file():
    """🔥 自动扫描 input 目录下最新的 excel/csv 文件"""
    if not os.path.exists(INPUT_DIR):
        print(f"{Fore.RED}❌ 目录不存在: {INPUT_DIR}")
        print(f"👉 请手动新建文件夹: data/input")
        return None

    # 搜索所有 csv, xls, xlsx
    files = glob.glob(os.path.join(INPUT_DIR, "*.csv")) + \
            glob.glob(os.path.join(INPUT_DIR, "*.xls")) + \
            glob.glob(os.path.join(INPUT_DIR, "*.xlsx"))

    if not files:
        print(f"{Fore.RED}❌ 在 {INPUT_DIR} 下未找到任何数据文件！{Fore.RESET}")
        print("👉 请确保你已经把同花顺导出的文件复制进去了。")
        return None

    # 按修改时间排序，取最新的一个
    latest_file = max(files, key=os.path.getmtime)
    print(f"{Fore.CYAN}📂 自动锁定最新文件: {os.path.basename(latest_file)}{Fore.RESET}")
    return latest_file


def load_file_content(filepath):
    """读取文件内容"""
    try:
        if filepath.endswith('.csv'):
            try:
                return pd.read_csv(filepath, dtype=str, encoding='gbk')
            except:
                try:
                    return pd.read_csv(filepath, dtype=str, encoding='utf-8')
                except:
                    return pd.read_csv(filepath, dtype=str, encoding='utf-16')
        else:
            return pd.read_excel(filepath, dtype=str)
    except Exception as e:
        print(f"{Fore.RED}❌ 文件读取失败: {e}")
        return None


def main():
    target_file = find_latest_data_file()
    if not target_file: return

    df = load_file_content(target_file)
    if df is None: return

    # 模糊匹配列名
    col_code = next((c for c in df.columns if "代码" in c), None)
    col_industry = next((c for c in df.columns if "行业" in c), None)
    col_concept = next((c for c in df.columns if "概念" in c or "题材" in c), None)

    if not col_code:
        print(f"{Fore.RED}❌ 无法识别‘代码’列，请检查文件内容是否正确。{Fore.RESET}")
        print(f"当前列名: {df.columns.tolist()}")
        return

    print(f"✅ 识别列: 行业=[{col_industry}]  概念=[{col_concept}]")

    db = {}
    count = 0

    for _, row in df.iterrows():
        raw_code = str(row[col_code]).strip()
        code = re.sub(r'\D', '', raw_code)
        if len(code) != 6: continue

        industry = str(row[col_industry]).strip() if col_industry else "未知"
        if industry == 'nan': industry = ""
        industry = industry.replace("二级行业", "").replace("一级行业", "")

        raw_concept = str(row[col_concept]).strip() if col_concept else ""
        concepts = clean_concepts(raw_concept)

        full_tag = f"{industry} | {concepts}" if concepts else industry
        db[code] = full_tag
        count += 1

    # 保存
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir): os.makedirs(db_dir)

    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"{Fore.GREEN}🎉 成功导入 {count} 条数据！数据库已更新。{Fore.RESET}")
    print(f"💡 现在再次运行 realtime_watch.py 即可生效。")


if __name__ == "__main__":
    main()