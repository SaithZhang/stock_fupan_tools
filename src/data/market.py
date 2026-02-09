# ==============================================================================
# 📊 市场逻辑分析器 (src/data/market.py)
# 职责：纯计算逻辑 (Brain)。接收数据 -> 返回指标。
# 包含：
# 1. MarketAnalyzer - 情绪周期、连板梯队、板块热度
# 2. TechnicalAnalyzer - 均线、乖离率、形态识别
# ==============================================================================

import numpy as np
from typing import List, Dict, Tuple
from collections import Counter

# 尝试导入配置，用于板块热度关键词
try:
    from src.config.settings import Config

    CORE_KEYWORDS = Config.CORE_KEYWORDS
except ImportError:
    CORE_KEYWORDS = ["算力", "低空", "芯片", "华为", "新能源", "医药"]  # 默认兜底


class MarketAnalyzer:
    @staticmethod
    def calculate_stats(all_data: List[Dict], yesterday_data: Dict) -> Dict:
        """
        计算全市场核心统计 (涨跌停数、最高板、昨日溢价)
        Args:
            all_data: 今日全市场个股数据列表
            yesterday_data: 昨日全市场个股数据字典 {code: item}
        """
        stats = {
            'limit_up_count': 0,
            'limit_down_count': 0,
            'highest_space': 0,
            'yesterday_limit_up_premium': 0
        }

        # 提取昨日涨停的股票代码
        yest_zt_codes = {c for c, v in yesterday_data.items() if v.get('is_zt')}

        total_premium = 0
        valid_premium_count = 0

        for item in all_data:
            # 排除 ST 和退市整理
            if 'ST' in str(item.get('name', '')).upper(): continue

            pct = item.get('today_pct', 0)
            limit_days = item.get('limit_days', 0)

            # 统计涨跌停
            if pct > 9.8: stats['limit_up_count'] += 1
            if pct < -9.0: stats['limit_down_count'] += 1

            # 统计最高板
            if limit_days > stats['highest_space']:
                stats['highest_space'] = limit_days

            # 计算昨日涨停溢价 (只计算今日还在池子里的)
            if item['code'] in yest_zt_codes:
                total_premium += item.get('open_pct', 0)
                valid_premium_count += 1

        if valid_premium_count > 0:
            stats['yesterday_limit_up_premium'] = round(total_premium / valid_premium_count, 2)

        return stats

    @staticmethod
    def analyze_phase(pool_data: List[Dict], market_stats: Dict) -> Dict:
        """
        基于策略选出的股票池，判定当前情绪周期
        """
        phase_info = {"phase": "未知", "action_guide": "观察"}

        # 1. 量能分析 (基于选出股票的量比)
        valid_vols = [x['vol_ratio'] for x in pool_data if x.get('vol_ratio', 0) > 0]
        avg_vol_ratio = sum(valid_vols) / len(valid_vols) if valid_vols else 1.0
        is_shrinking = avg_vol_ratio < 0.85

        # 2. 板块热度统计
        sector_counter = Counter()
        total_zt_in_pool = 0

        for item in pool_data:
            # 只统计大涨的票
            if item.get('today_pct', 0) > 5.0:
                total_zt_in_pool += 1
                tags = str(item.get('tag', '')).split('/')
                # 优先匹配核心关键词
                found_key = "其他"
                for t in tags:
                    if t in CORE_KEYWORDS:
                        found_key = t
                        break
                sector_counter[found_key] += 1

        # 移除"其他"干扰，取出前三
        if "其他" in sector_counter: del sector_counter["其他"]
        top3 = sector_counter.most_common(3)

        # 3. 周期判定逻辑
        # 主线集中度
        top_count = sum([x[1] for x in top3])
        concentration = (top_count / total_zt_in_pool) if total_zt_in_pool > 0 else 0

        if is_shrinking:
            if concentration > 0.5:
                phase_info["phase"] = "📉 缩量抱团"
                phase_info["action_guide"] = "聚焦前排核心，后排易掉队"
            else:
                phase_info["phase"] = "🌪️ 缩量轮动/退潮"
                phase_info["action_guide"] = "空仓或试错首板，切忌追高"
        else:
            if concentration > 0.6:
                phase_info["phase"] = "🚀 主线主升"
                phase_info["action_guide"] = "积极做多核心板块"
            else:
                phase_info["phase"] = "⚔️ 放量分歧/混战"
                phase_info["action_guide"] = "去弱留强，关注弱转强卡位"

        phase_info['top_sectors'] = [x[0] for x in top3]
        return phase_info


class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(history_df, current_price: float) -> Tuple[List[str], Dict]:
        """计算个股技术指标 (均线/乖离)"""
        tags = []
        indicators = {}
        if history_df is None or len(history_df) < 5:
            return tags, indicators

        # 确保按日期升序
        df = history_df.sort_values('trade_date')
        closes = df['close'].values

        ma5 = np.mean(closes[-5:]) if len(closes) >= 5 else 0
        ma10 = np.mean(closes[-10:]) if len(closes) >= 10 else 0
        ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else 0

        # 乖离率
        bias_5 = (current_price - ma5) / ma5 if ma5 > 0 else 0

        # 简单的多头排列判断
        is_bullish = (ma5 > ma10) and (current_price > ma20)

        if is_bullish:
            if -0.02 <= bias_5 <= 0.02:
                tags.append("🎯5日线低吸")
            elif bias_5 > 0.08:
                tags.append("🚀趋势加速")  # 乖离过大
            else:
                tags.append("🌊趋势向上")

        return tags, indicators

    @staticmethod
    def check_special_shape(item: Dict) -> Tuple[List[str], str]:
        """判断涨停形态"""
        tags = []
        limit_type = ""

        if item.get('is_zt'):
            open_pct = item.get('open_pct', 0)
            # 简单判断：如果开盘也是涨停，且中间没打开过(这个信息通常需要分时数据，这里简化近似)
            # 严格的一字板需要 high == low == open == close

            if open_pct > 9.8:
                limit_type = "T字/一字"
            else:
                limit_type = "换手板"

            if item.get('is_broken'):  # 如果炸过板
                tags.append("💔曾炸板")

        return tags, limit_type