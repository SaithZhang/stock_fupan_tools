# src/config/pool_config.py
import os

# --- 1. 基础路径 ---
# 假设本文件在 src/config/ 下，向上回溯3级找到项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 输入目录
INPUT_AK_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'akshare')
INPUT_THS_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')
RISK_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'risk')
DAPAN_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'dapan')

# 列表文件
HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')
MANUAL_FOCUS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'manual_focus.txt')

# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')
LHB_DIR = os.path.join(OUTPUT_DIR, 'lhb')

# --- 2. 业务常量 ---
# 联动大哥映射 (小弟: 大哥)
LINK_DRAGON_MAP = {
    '002009': '002931',
}

# 核心概念关键词 (用于提取自动标签)
CORE_KEYWORDS = [
    '机器人', '航天', '军工', '卫星', '低空', 'AI', '人工智能',
    '智能体', '算力', 'CPO', '存储', '消费电子', '华为', '信创', 
    '数字货币', '数据要素', '文化传媒', '短剧', '多模态', '纺织', 
    '并购重组', '固态电池', '自动驾驶'
]