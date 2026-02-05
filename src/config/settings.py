# ==============================================================================
# 📌 全局配置 (src/config/settings.py)
# 集中管理路径、核心关键词、策略参数
# ==============================================================================

import os
import sys


class Config:
    # --- 路径配置 ---
    # 假设结构为: project/src/config/settings.py
    # 向两级获取到 project/src，再向上一级获取 project root
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _src_dir = os.path.dirname(_current_dir)
    PROJECT_ROOT = os.path.dirname(_src_dir)

    OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
    ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')
    INPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'input')
    CALL_AUCTION_DIR = os.path.join(INPUT_DIR, 'call_auction')

    # 具体文件路径
    HOLDINGS_PATH = os.path.join(INPUT_DIR, 'holdings.txt')
    F_LAO_PATH = os.path.join(INPUT_DIR, 'f_lao_list.txt')
    MANUAL_FOCUS_PATH = os.path.join(INPUT_DIR, 'manual_focus.txt')
    RISK_DIR = os.path.join(INPUT_DIR, 'risk')
    THS_DIR = os.path.join(INPUT_DIR, 'ths')
    DAPAN_DIR = os.path.join(INPUT_DIR, 'dapan')
    LHB_DIR = os.path.join(OUTPUT_DIR, 'lhb')

    # --- 策略配置 ---

    # 核心题材关键词 (便于全局修改)
    CORE_KEYWORDS = [
        # --- 1.26 新增/重点方向 ---
        '光伏', '胶膜', '玻璃',  # 太空光伏产业链
        '化工', '有色', '铜',  # 强趋势轮动
        'PCB', '核聚变', '核电',  # 轮动题材
        '封装', '锂电池',  # 细分科技/新能源

        # --- 原有核心 ---
        '机器人', '电机', '丝杠',
        '航天', '军工', '卫星', '低空',
        '电网', '电力',
        'AI', '人工智能', '智能体', '算力', 'CPO', '存储', '半导体',
        '消费电子', '华为', '信创', '数据要素',
        '文化传媒', '短剧', '固态电池', '自动驾驶'
    ]

    # 特殊持仓策略映射 (Code -> [Tag, LinkDragon])
    HOLDING_STRATEGIES = {}

    # 龙一龙二关联映射 (Code -> DragonCode)
    LINK_DRAGON_MAP = {'002009': '002931'}


# 调试用：打印路径确认
if __name__ == "__main__":
    print(f"Project Root: {Config.PROJECT_ROOT}")
    print(f"Output Dir:   {Config.OUTPUT_DIR}")