# ==============================================================================
# 📂 数据加载器 (src/data/loader.py)
# 负责从磁盘读取历史策略池、龙虎榜、风险监控数据
# ==============================================================================

import os
import pandas as pd
import re
from datetime import datetime
from colorama import Fore
from typing import Dict, Set, Tuple

# 引入配置
try:
    from src.config.settings import Config
except ImportError:
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.config.settings import Config


class SystemDataLoader:
    """
    负责加载系统生成的中间文件或手工维护的特殊数据
    (区别于基础行情数据的加载)
    """

    @staticmethod
    def load_yesterday_pool() -> Dict[str, Dict]:
        """加载最近一期的策略池 (兼容 v2 和旧格式)"""
        if not os.path.exists(Config.OUTPUT_DIR): return {}

        files = []
        today_str = datetime.now().strftime("%Y%m%d")

        # 扫描 output 和 archive 目录
        for d in [Config.OUTPUT_DIR, Config.ARCHIVE_DIR]:
            if not os.path.exists(d): continue
            for f in os.listdir(d):
                # 1. 基础过滤：必须是 csv 且包含 strategy_pool
                if not (f.startswith('strategy_pool') and f.endswith('.csv')):
                    continue

                # 2. 正则提取日期 (兼容 strategy_pool_2026... 和 strategy_pool_v2_2026...)
                # 寻找文件名中的连续8位数字
                match = re.search(r'(\d{8})', f)
                if match:
                    date_part = match.group(1)
                    # 确保是过去的文件
                    if date_part < today_str:
                        files.append({'path': os.path.join(d, f), 'date': date_part})

        if not files:
            # 只有当真的找不到文件时才警告（静默失败通常是因为是假期或第一天）
            # print(f"{Fore.YELLOW}⚠️ 未找到昨日(或更早)的策略池文件...")
            return {}

        # 按日期倒序，取最近一份
        files.sort(key=lambda x: x['date'], reverse=True)
        target_file = files[0]['path']
        print(f"{Fore.BLUE}🔙 回溯历史数据: {os.path.basename(target_file)}")

        res_map = {}
        try:
            df = pd.read_csv(target_file, dtype={'code': str, 'sina_code': str})
            for _, row in df.iterrows():
                # 兼容 sina_code 和 code 字段
                c = str(row.get('code', '')).zfill(6)
                if not c or c == '000000':
                    raw_sina = str(row.get('sina_code', ''))
                    c = raw_sina[-6:] if len(raw_sina) >= 6 else ''

                tag = str(row.get('tag', ''))
                if "炸板" in tag:
                    res_map[c] = {'amount': float(row.get('amount', 0)), 'tag': tag}
        except Exception as e:
            print(f"{Fore.RED}❌ 读取历史文件失败: {e}")
        return res_map

    @staticmethod
    def load_lhb_info() -> Tuple[Set[str], Dict[str, Set[str]]]:
        """加载龙虎榜和游资席位数据"""
        lhb_path = os.path.join(Config.LHB_DIR, 'lhb_latest.csv')
        seat_path = os.path.join(Config.LHB_DIR, 'lhb_famous_latest.csv')

        lhb_codes = set()
        seat_map = {}

        if os.path.exists(lhb_path):
            try:
                df = pd.read_csv(lhb_path, dtype=str)
                if '代码' in df.columns:
                    lhb_codes = set(df['代码'].apply(lambda x: str(x).strip().zfill(6)).tolist())
            except Exception as e:
                print(f"{Fore.RED}❌ LHB加载失败: {e}")

        if os.path.exists(seat_path):
            try:
                df = pd.read_csv(seat_path, dtype=str)
                for _, row in df.iterrows():
                    label = row['游资标签']

                    # 内部辅助函数：解析龙虎榜字符串
                    def parse_lhb_str(raw_str, default_prefix):
                        if not raw_str or raw_str == 'nan': return
                        for p in raw_str.split(' '):
                            p = p.strip()
                            if not p: continue

                            s_name = p.split('(')[0]
                            note = f"({p.split('(')[1].rstrip(')')})" if '(' in p else ""

                            tag_info = ""
                            if '/' in s_name:
                                s_name, tag_part = s_name.split('/')[:2]
                                tag_info = f"/{tag_part}"

                            if s_name not in seat_map: seat_map[s_name] = set()

                            prefix = default_prefix
                            if "锁仓" in note or "锁仓" in p:
                                prefix = "🔒"
                            elif "加仓" in note:
                                prefix = "➕"

                            seat_map[s_name].add(f"{prefix}{label}{tag_info}{note}")

                    parse_lhb_str(str(row.get('买入股票', '')), "💰")
                    parse_lhb_str(str(row.get('卖出股票', '')), "🏃")
            except Exception as e:
                print(f"{Fore.RED}❌ 游资数据加载失败: {e}")

        return lhb_codes, seat_map

    @staticmethod
    def load_risk_data() -> Dict[str, Dict]:
        """加载手工维护的异动风险表"""
        print(f"{Fore.MAGENTA}🔎 正在加载异动风险数据 (手动文件)...")
        risk_map = {}
        try:
            if not os.path.exists(Config.RISK_DIR):
                print(f"   ⚠️ 未找到风险文件夹: {Config.RISK_DIR}")
                return {}

            risk_files = [f for f in os.listdir(Config.RISK_DIR) if f.startswith('risk_') and f.endswith('.csv')]
            if not risk_files: return {}

            risk_files.sort(reverse=True)
            target_file = os.path.join(Config.RISK_DIR, risk_files[0])
            print(f"   📄 找到文件: {risk_files[0]}")

            df = pd.read_csv(target_file)
            for _, row in df.iterrows():
                name = str(row['股票名称']).strip()
                msg = str(row.get('当前累计偏离值', ''))
                rule = str(row.get('监管规则', ''))

                match = re.search(r'(-?\d+\.?\d*)%', msg)
                val = float(match.group(1)) if match else 0.0

                risk_map[name] = {
                    'risk_level': str(row.get('风险等级', '🟢 Safe')),
                    'risk_msg': msg,
                    'risk_rule': rule,
                    'trigger_next': str(row.get('异动触发条件', '')),
                    'deviation_val_10d': val if '10日' in rule else 0.0,
                    'deviation_val_30d': val if '30日' in rule else 0.0
                }
        except Exception as e:
            print(f"{Fore.RED}⚠️ 读取CSV失败: {e}")
        return risk_map