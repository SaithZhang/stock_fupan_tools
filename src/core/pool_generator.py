# ==============================================================================
# 📌 策略池生成器 (src/core/pool_generator.py) - 【盘后运行】
# Version: 1.3 (Refactored) | Last Modified: 2026-01-21
# Update: 重构代码结构，保持逻辑不变，增强可读性与模块化
# ==============================================================================

import pandas as pd
import os
import shutil
import sys
import re
import json
import numpy as np
from datetime import datetime
from colorama import init, Fore
from typing import Dict, List, Set, Tuple, Any, Optional

# ================= 0. 环境初始化与依赖加载 =================

init(autoreset=True)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

# 动态添加路径
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

# 核心模块导入
try:
    from data_loader import get_merged_data, load_yesterday_ths_data
    from market_data import MarketDataManager

    # 策略模块
    sys.path.append(os.path.join(project_root, 'src', 'strategies'))
    from ddd_mode import get_ddd_pool_category
    from f_lao_model import load_ths_history, check_fen_jue
except ImportError as e:
    # 允许部分模块缺失，但不中断核心流程（依据原逻辑）
    print(f"{Fore.YELLOW}⚠️ 核心/策略模块加载警告: {e}")


    # 定义兜底函数
    def get_merged_data():
        return []


    def load_yesterday_ths_data():
        return {}


    def load_ths_history(*args, **kwargs):
        return {}


    def check_fen_jue(*args):
        return []


    def get_ddd_pool_category(*args):
        return None

# 筹码分析模块导入 (可选)
try:
    from tools.chip_analyzer import get_chip_metrics, generate_chip_tag

    print(f"{Fore.GREEN}✅ 筹码分析模块加载成功")
except ImportError as e:
    print(f"{Fore.YELLOW}⚠️ 筹码分析模块加载失败: {e} (将跳过筹码分析)")


    def get_chip_metrics(*args):
        return None


    def generate_chip_tag(*args):
        return ""


    print(f"{Fore.GREEN}✅ DDD模式模块加载成功")  # 保持原输出顺序


# ================= 1. 配置与常量定义 =================

class Config:
    PROJECT_ROOT = project_root
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
    ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')
    INPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'input')

    # 文件路径
    HOLDINGS_PATH = os.path.join(INPUT_DIR, 'holdings.txt')
    F_LAO_PATH = os.path.join(INPUT_DIR, 'f_lao_list.txt')
    MANUAL_FOCUS_PATH = os.path.join(INPUT_DIR, 'manual_focus.txt')
    RISK_DIR = os.path.join(INPUT_DIR, 'risk')
    THS_DIR = os.path.join(INPUT_DIR, 'ths')
    DAPAN_DIR = os.path.join(INPUT_DIR, 'dapan')
    LHB_DIR = os.path.join(OUTPUT_DIR, 'lhb')

    # 策略配置
    CORE_KEYWORDS = [
        '机器人', '航天', '军工', '卫星', '低空', '电网', '电力',
        'AI', '人工智能', '智能体', '算力', 'CPO', '存储', '半导体',
        '消费电子', '华为', '信创', '数字货币', '数据要素',
        '文化传媒', '短剧', '多模态', '纺织', '并购重组', '固态电池', '自动驾驶'
    ]

    HOLDING_STRATEGIES = {}
    LINK_DRAGON_MAP = {'002009': '002931'}


# ================= 2. 工具类与辅助函数 =================

class TextUtils:
    @staticmethod
    def format_sina_code(code: str) -> str:
        code = str(code)
        if code.startswith('6'): return f"sh{code}"
        if code.startswith(('8', '4')): return f"bj{code}"
        return f"sz{code}"

    @staticmethod
    def get_link_dragon(code: str) -> str:
        """获取关联的大哥代码"""
        if code in Config.HOLDING_STRATEGIES:
            dragon = Config.HOLDING_STRATEGIES[code][1]
            if dragon: return dragon

        dragon = Config.LINK_DRAGON_MAP.get(code, '')
        if dragon:
            if dragon.startswith(('sz', 'sh')): return dragon
            return TextUtils.format_sina_code(dragon)
        return ''

    @staticmethod
    def clean_manual_tag(tag: str, is_zt_tag_present: bool) -> str:
        if not tag: return ""
        if tag.startswith("F佬/"):
            tag = tag[3:]
        elif tag.startswith("F佬"):
            tag = tag.lstrip("F佬").lstrip("/")

        if is_zt_tag_present:
            tag = re.sub(r'(^|/|[(])\d+板([)]|/|$)', r'\1\2', tag)
            tag = tag.replace('()', '').replace('//', '/').replace('(/', '(').replace('/)', ')')
            tag = tag.strip('/')
        return tag

    @staticmethod
    def get_unique_concepts(base_str: str, new_concepts_str: str) -> str:
        if not new_concepts_str: return ""
        base_parts = re.split(r'[/()]', base_str)
        base_set = set(p.strip() for p in base_parts if p.strip())

        final_new = []
        for c in new_concepts_str.split('/'):
            c = c.strip()
            if c and c not in base_set and c not in base_str:
                final_new.append(c)
        return "/".join(final_new)

    @staticmethod
    def get_core_concepts_local(name: str, raw_tag: str) -> str:
        matched = set()
        source_text = f"{name} {raw_tag}"
        for key in Config.CORE_KEYWORDS:
            if key in source_text:
                matched.add(key)
        return "/".join(list(matched))

    @staticmethod
    def load_text_list(filepath: str) -> Dict[str, str]:
        if not os.path.exists(filepath): return {}
        mapping = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = re.split(r'\s+', line, maxsplit=1)
                    code = parts[0].strip().replace("SZ", "").replace("SH", "")
                    if code.isdigit() and len(code) == 6:
                        tag = parts[1].strip() if len(parts) > 1 else "关注"
                        mapping[code] = tag
        except Exception as e:
            print(f"{Fore.RED}加载列表失败 {filepath}: {e}")
        return mapping


class DataLoader:
    @staticmethod
    def load_yesterday_pool() -> Dict[str, Dict]:
        """加载最近一期的策略池寻找昨日炸板股"""
        if not os.path.exists(Config.OUTPUT_DIR): return {}

        files = []
        today_str = datetime.now().strftime("%Y%m%d")

        # 扫描 output 和 archive 目录
        for d in [Config.OUTPUT_DIR, Config.ARCHIVE_DIR]:
            if not os.path.exists(d): continue
            for f in os.listdir(d):
                if f.startswith('strategy_pool_') and f.endswith('.csv'):
                    date_part = f.replace('strategy_pool_', '').replace('.csv', '')
                    if date_part.isdigit() and date_part < today_str:
                        files.append({'path': os.path.join(d, f), 'date': date_part})

        if not files:
            print(f"{Fore.YELLOW}⚠️ 未找到昨日(或更早)的策略池文件，无法执行[断板反包]策略")
            return {}

        files.sort(key=lambda x: x['date'], reverse=True)
        target_file = files[0]['path']
        print(f"{Fore.BLUE}🔙 回溯历史数据: {os.path.basename(target_file)}")

        res_map = {}
        try:
            df = pd.read_csv(target_file, dtype={'code': str})
            for _, row in df.iterrows():
                c = str(row['code']).zfill(6)
                tag = str(row.get('tag', ''))
                if "炸板" in tag:
                    res_map[c] = {'amount': float(row.get('amount', 0)), 'tag': tag}
        except Exception as e:
            print(f"{Fore.RED}❌ 读取历史文件失败: {e}")
        return res_map

    @staticmethod
    def load_lhb_info() -> Tuple[Set[str], Dict[str, Set[str]]]:
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


# ================= 3. 市场与技术分析逻辑 =================

class MarketAnalyzer:
    @staticmethod
    def calculate_stats(all_data, yesterday_data):
        stats = {'limit_up_count': 0, 'limit_down_count': 0, 'highest_space': 0}
        yest_zt_codes = [c for c, v in yesterday_data.items() if v.get('is_zt')]

        total_premium = 0
        valid_premium_count = 0

        for item in all_data:
            if 'ST' in item['name'].upper(): continue
            pct = item.get('today_pct', 0)

            if pct > 9.8: stats['limit_up_count'] += 1
            if pct < -9.0: stats['limit_down_count'] += 1
            stats['highest_space'] = max(stats['highest_space'], item.get('limit_days', 0))

            # 计算昨日涨停溢价
            if item['code'] in yest_zt_codes:
                total_premium += item.get('open_pct', 0)
                valid_premium_count += 1

        stats['yesterday_limit_up_premium'] = round(total_premium / valid_premium_count,
                                                    2) if valid_premium_count > 0 else 0
        return stats

    @staticmethod
    def analyze_phase(pool_data, market_stats):
        phase_info = {"phase": "未知", "action_guide": ""}

        valid_vols = [x['vol_ratio'] for x in pool_data if x.get('vol_ratio', 0) > 0]
        avg_vol_ratio = sum(valid_vols) / len(valid_vols) if valid_vols else 1.0
        is_shrinking = avg_vol_ratio < 0.85

        sector_counts = {}
        total_zt = 0
        for item in pool_data:
            if item.get('today_pct', 0) > 9.0:
                total_zt += 1
                found = "其他"
                for t in str(item.get('tag', '')).split('/'):
                    if t in Config.CORE_KEYWORDS: found = t; break
                sector_counts[found] = sector_counts.get(found, 0) + 1

        top3 = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        concentration = (sum([x[1] for x in top3]) / total_zt) if total_zt > 0 else 0

        if is_shrinking:
            phase_info["phase"] = "🌪️ 缩量轮动" if concentration < 0.5 else "📉 缩量抱团"
            phase_info["action_guide"] = "量能不足，切忌追高。策略：低吸核心做T，或潜伏死鱼。"
        else:
            phase_info["phase"] = "🚀 主线主升" if concentration > 0.6 else "⚔️ 放量分歧"
            phase_info["action_guide"] = "积极做多核心" if concentration > 0.6 else "去弱留强，关注弱转强"

        phase_info['top_sectors'] = [x[0] for x in top3]
        return phase_info


class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(history_df, current_price):
        tags = []
        indicators = {}
        if history_df is None or len(history_df) < 5: return tags, indicators

        df = history_df.sort_values('date')
        closes = df['close'].values

        ma5 = np.mean(closes[-5:]) if len(closes) >= 5 else 0
        ma10 = np.mean(closes[-10:]) if len(closes) >= 10 else 0
        ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else 0

        bias_5 = (current_price - ma5) / ma5 if ma5 > 0 else 0
        is_bullish_trend = (ma5 > ma10) and (current_price > ma20)

        if is_bullish_trend:
            if -0.01 <= bias_5 <= 0.025:
                tags.append("🎯5日线低吸")
            elif bias_5 > 0.05:
                tags.append("🚀趋势加速")
            tags.append("🌊趋势向上")

        if len(closes) > 5:
            recent_volatility = np.std(closes[-5:]) / np.mean(closes[-5:])
            if recent_volatility < 0.02 and current_price > ma20:
                tags.append("🐟死鱼/待启动")

        return tags, indicators

    @staticmethod
    def check_special_shape(item):
        tags = []
        limit_type = ""
        if item.get('is_zt'):
            open_pct = item.get('open_pct', 0)
            open_num = item.get('open_num', 0)

            if open_pct > 9.0:
                limit_type = "一字" if open_num == 0 else "T字"
            else:
                limit_type = "换手板"

            if open_num > 5: limit_type += "/烂板"

        return tags, limit_type


# ================= 4. 主生成器逻辑 =================

class PoolGenerator:
    def __init__(self):
        self.all_data = []
        self.holdings_map = {}
        self.f_lao_map = {}
        self.manual_recognition_map = {}
        self.broken_pool_map = {}
        self.lhb_codes = set()
        self.lhb_seat_map = {}
        self.history_map = {}
        self.yest_full_data = {}
        self.md_manager = None
        self.risk_map = {}

    def load_all_data(self):
        """统一加载所有数据源"""
        self.all_data = get_merged_data()
        if not self.all_data:
            print(f"{Fore.RED}❌ 数据源为空")
            return False

        self.holdings_map = TextUtils.load_text_list(Config.HOLDINGS_PATH)
        self.f_lao_map = TextUtils.load_text_list(Config.F_LAO_PATH)
        self.manual_recognition_map = TextUtils.load_text_list(Config.MANUAL_FOCUS_PATH)
        self.broken_pool_map = DataLoader.load_yesterday_pool()
        self.lhb_codes, self.lhb_seat_map = DataLoader.load_lhb_info()

        print(f"{Fore.MAGENTA}🔙 正在加载昨日全量数据以计算竞价/溢价...")
        self.yest_full_data = load_yesterday_ths_data()

        self.md_manager = MarketDataManager(Config.DAPAN_DIR)
        market_loaded = self.md_manager.load_data()

        print(f"{Fore.MAGENTA} 正在加载最近5日历史数据 (for F佬模型)...")
        self.history_map = load_ths_history(Config.THS_DIR, days=30)

        if market_loaded:
            print(f"   ✅ {self.md_manager.get_formatted_summary()}")
        else:
            print(f"   ⚠️ warning: 未找到大盘数据")

        return True

    def process_item(self, item) -> Optional[Dict]:
        """单只股票处理逻辑"""
        code = str(item['code'])
        name = item['name']
        pct = item.get('today_pct', 0)
        price = item.get('price', 0)  # 关键：必须添加此行

        if 'ST' in name.upper(): return None

        is_holding = (code in self.holdings_map)
        raw_tag_str = str(item.get('tag', '')).replace('nan', '')

        base_tags = []
        is_selected = False
        is_zt = item.get('is_zt') or (pct >= 9.8)

        # --- 1. 基础涨停标签 ---
        zt_tag = ""
        if is_zt:
            limit_days = item.get('limit_days', 0) + 1
            zt_tag = f"{limit_days}板" if limit_days > 1 else "首板"
            if item.get('open_num', 0) > 0:
                zt_tag += f"/回封(炸{item.get('open_num')}次)"
            elif item.get('is_first_limit'):
                zt_tag += "/硬板"

        # --- 2. 策略身份判定 ---
        manual_cleaned_tag = ""

        # 2.1 关注/持仓
        base_focus = {**self.f_lao_map, **self.holdings_map}
        if code in base_focus:
            is_selected = True
            if code in Config.HOLDING_STRATEGIES:
                tag = Config.HOLDING_STRATEGIES[code][0]
                base_tags.append(tag)
                manual_cleaned_tag = tag
            elif is_holding:
                tag = f"持仓/{name}"
                base_tags.append(tag)
                manual_cleaned_tag = tag
            else:
                raw_note = self.f_lao_map[code]
                cleaned_note = TextUtils.clean_manual_tag(raw_note, is_zt)
                final_manual = f"F佬/{cleaned_note}" if cleaned_note != "关注" else "F佬/关注"
                base_tags.append(final_manual)
                manual_cleaned_tag = final_manual

        # 2.2 龙虎榜
        if code in self.lhb_codes:
            is_selected = True
            base_tags.append("🐉龙虎榜")

        if name in self.lhb_seat_map:
            is_selected = True

            def tag_sort(t):
                if t.startswith(("🔒", "➕")): return 0
                if t.startswith("💰"): return 1
                if t.startswith("🏃"): return 2
                return 3

            base_tags.extend(sorted(list(self.lhb_seat_map[name]), key=tag_sort))

        # 2.3 辨识度/人气
        is_popular = False
        pop_reasons = set()
        if code in self.manual_recognition_map or name in self.manual_recognition_map:
            is_popular = True
        if item.get('limit_days', 0) >= 3:
            is_popular = True
        if item.get('amount', 0) >= 20_0000_0000:
            is_popular = True
            pop_reasons.add("成交")

        if is_popular:
            is_selected = True
            base_tags.append("★人气")
            if pop_reasons: base_tags.extend(sorted(list(pop_reasons)))

        # 2.4 断板反包
        if code in self.broken_pool_map and pct > 0:
            is_selected = True
            yest_amt = self.broken_pool_map[code]['amount']
            label = "🔥断板反包"
            if yest_amt > 10000 and item.get('amount', 0) > yest_amt:
                label += "/爆量"
            base_tags.append(label)

        # 2.5 焚诀模型
        if code in self.history_map:
            f_tags = check_fen_jue(self.history_map[code])
            if f_tags:
                base_tags.extend(f_tags)
                is_selected = True

        # 2.6 DDD模式
        ddd_tag = get_ddd_pool_category(item)
        if ddd_tag:
            is_selected = True
            base_tags.append(ddd_tag)

        # 2.7 技术分析
        if is_selected or item.get('limit_days', 0) >= 2:
            tech_tags, _ = TechnicalAnalyzer.calculate_indicators(self.history_map.get(code), price)
            if tech_tags:
                base_tags.extend(tech_tags)
                if "🎯5日线低吸" in tech_tags: is_selected = True

        # --- 3. 标签组装与修正 ---
        if is_zt:
            is_selected = True
            base_tags.append(zt_tag)

        # 炸板检测
        is_zb = "炸板" in raw_tag_str or (item.get('max_pct', 0) > 9.0 and pct < 9.0)
        if is_zb and pct > -7.0:
            is_selected = True
            base_tags.append("👀焚诀预期/炸板")

        # 跌停检测
        if pct <= -9.0:
            is_selected = True
            base_tags.append("📉跌停/博弈修复")

        # 大额补录
        if (item.get('amount', 0) / 100000000.0) > 20.0 and pct > 0:
            is_selected = True

        # 筹码分析 (仅对关键股)
        if is_selected and (is_holding or code in self.broken_pool_map or item.get('limit_days', 0) >= 3):
            print(f"   🔎 分析筹码: {name} ({code}) ...", end="")
            chip_metrics = get_chip_metrics(code)
            if chip_metrics:
                chip_tag = generate_chip_tag(chip_metrics)
                if chip_tag:
                    base_tags.append(chip_tag)
                    print(f" {Fore.YELLOW}Tags: {chip_tag}")
                else:
                    print(" (无显著特征)")
            else:
                print(" (数据获取失败)")

        if not is_selected: return None

        # 最终合并
        local_concepts = TextUtils.get_core_concepts_local(name, raw_tag_str)
        unique_concepts = TextUtils.get_unique_concepts(manual_cleaned_tag, local_concepts)

        shape_tags, zt_type = TechnicalAnalyzer.check_special_shape(item)
        if zt_type:
            base_tags.append(f"[{zt_type}]")
            item['limit_up_type'] = zt_type
        else:
            item['limit_up_type'] = ""

        # 集合竞价比例
        yest_item = self.yest_full_data.get(code)
        call_auc_ratio = 0.0
        if yest_item and yest_item.get('amount', 0) > 0:
            call_auc_ratio = item.get('call_auction_amount', 0) / yest_item['amount']

        # 标签去重与格式化
        final_parts = []
        final_parts.extend(base_tags)
        if unique_concepts: final_parts.append(unique_concepts)
        final_parts.extend(shape_tags)

        seen = set()
        clean_parts = [p for p in final_parts if not (p in seen or seen.add(p))]

        final_tag_str = "/".join(clean_parts).replace('//', '/')
        final_tag_str = final_tag_str.replace("🔥断板反包", "🔥A大焚诀")
        final_tag_str = final_tag_str.replace("🎯5日线低吸", "🎯5日线低吸(F佬推荐)")

        # 构造结果行
        return {
            'sina_code': TextUtils.format_sina_code(code),
            'name': name,
            'tag': final_tag_str,
            'amount': item.get('amount', 0),
            'last_amount': yest_item.get('amount', 0) if yest_item else 0,
            'today_pct': pct,
            'turnover': item.get('turnover', 0),
            'open_pct': item.get('open_pct', 0),
            'price': price,
            'pct_10': item.get('pct_10', 0),
            'link_dragon': TextUtils.get_link_dragon(code),
            'vol': item.get('vol', 0),
            'vol_prev': item.get('vol_prev', 0),
            'vol_ratio': item.get('vol_ratio', 0),
            'code': code,
            'call_auction_ratio': round(call_auc_ratio, 3)
        }

    def run(self):
        if not self.load_all_data(): return

        # 计算大盘统计数据
        market_stats = MarketAnalyzer.calculate_stats(self.all_data, self.yest_full_data)
        self.md_manager.update_extra_stats(market_stats)

        print(
            f"{Fore.CYAN}📋 离线生成启动 | 数据源: {len(self.all_data)}条 | 持仓: {len(self.holdings_map)} | 关注: {len(self.f_lao_map)} | LHB: {len(self.lhb_codes)}")

        pool = []
        for item in self.all_data:
            res = self.process_item(item)
            if res: pool.append(res)

        # 补录风险数据
        self.risk_map = DataLoader.load_risk_data()
        matches = 0
        for p in pool:
            info = self.risk_map.get(p['name'], {
                'risk_level': '🟢 Safe', 'risk_msg': '-', 'risk_rule': '',
                'trigger_next': '-', 'deviation_val_10d': 0.0, 'deviation_val_30d': 0.0
            })
            p.update(info)
            if p['name'] in self.risk_map: matches += 1
        print(f"   ✅ 成功匹配 {matches} 只标的风险数据")

        # 市场阶段判定
        phase_info = MarketAnalyzer.analyze_phase(pool, market_stats)
        market_stats.update(phase_info)
        print(f"\n{Fore.YELLOW}📊 市场状态判定: {phase_info['phase']}")
        print(f"   💡 {phase_info['action_guide']}")
        print(f"   🔥 领涨方向: {phase_info['top_sectors']}")

        # 导出结果
        if pool:
            df = pd.DataFrame(pool)
            df.sort_values(by='amount', ascending=False, inplace=True)

            # 补全可能缺失的列
            cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price',
                    'risk_level', 'risk_msg', 'trigger_next', 'risk_rule', 'deviation_val_10d', 'deviation_val_30d',
                    'call_auction_ratio', 'last_amount', 'limit_up_type',
                    'pct_10', 'link_dragon', 'vol', 'vol_prev', 'vol_ratio', 'code']
            for c in cols:
                if c not in df.columns: df[c] = 0
            df = df[cols]

            date_str = datetime.now().strftime("%Y%m%d")
            dated_path = os.path.join(Config.OUTPUT_DIR, f'strategy_pool_{date_str}.csv')
            latest_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')

            df.to_csv(dated_path, index=False, encoding='utf-8-sig')
            shutil.copyfile(dated_path, latest_path)

            # 导出市场 JSON
            try:
                final_json = self.md_manager.get_summary()
                final_json.update(market_stats)
                json_path = os.path.join(Config.OUTPUT_DIR, f'market_sentiment_{date_str}.json')
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(final_json, f, indent=2, ensure_ascii=False)
                print(f"📄 大盘数据: {json_path}")
            except Exception as e:
                print(f"❌ 导出大盘JSON失败: {e}")

            print(f"\n{Fore.GREEN}🎉 离线复盘完成！生成标的: {len(pool)} 只")
            print(f"📄 日期文件: {dated_path}")
            print(f"📄 通用文件: {latest_path} (已更新)")
        else:
            print(f"{Fore.RED}❌ 筛选结果为空。")


if __name__ == "__main__":
    generator = PoolGenerator()
    generator.run()