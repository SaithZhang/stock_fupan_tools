# ==============================================================================
# 📊 市场分析器 (src/data/market.py)
# 包含：
# 1. MarketAnalyzer - 计算全市场情绪、连板高度、主流板块
# 2. TechnicalAnalyzer - 计算个股均线、乖离率、形态
# ==============================================================================

import numpy as np
from typing import List, Dict, Tuple

# 引入配置 (用于获取 CORE_KEYWORDS 进行板块热度统计)
try:
    from src.config.settings import Config
except ImportError:
    import os, sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.config.settings import Config

class MarketAnalyzer:
    @staticmethod
    def calculate_stats(all_data: List[Dict], yesterday_data: Dict) -> Dict:
        """计算全市场统计数据 (涨跌停数、最高连板、昨日溢价)"""
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

        stats['yesterday_limit_up_premium'] = round(total_premium / valid_premium_count, 2) if valid_premium_count > 0 else 0
        return stats

    @staticmethod
    def analyze_phase(pool_data: List[Dict], market_stats: Dict) -> Dict:
        """基于选股结果，判定当前市场阶段 (情绪周期)"""
        phase_info = {"phase": "未知", "action_guide": ""}

        valid_vols = [x['vol_ratio'] for x in pool_data if x.get('vol_ratio', 0) > 0]
        avg_vol_ratio = sum(valid_vols) / len(valid_vols) if valid_vols else 1.0
        is_shrinking = avg_vol_ratio < 0.85

        # 统计板块热度 (基于 Config.CORE_KEYWORDS)
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
    def calculate_indicators(history_df, current_price: float) -> Tuple[List[str], Dict]:
        """计算均线、乖离率、波动率"""
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
    def check_special_shape(item: Dict) -> Tuple[List[str], str]:
        """判断涨停形态 (一字、T字、换手)"""
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