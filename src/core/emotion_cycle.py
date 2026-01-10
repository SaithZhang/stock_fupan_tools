# src/core/emotion_cycle.py

import akshare as ak
import pandas as pd
import datetime
from src.config import ProjectConfig

class EmotionalCycleEngine:
    def __init__(self):
        self.config = ProjectConfig()
        self.current_phase = self.config.PHASE_DIVERGENCE
        self.history_stats = []

    def fetch_market_mood(self, days=15):
        """
        获取最近N天的市场情绪数据:
        1. 涨停家数
        2. 连板最高高度
        3. 炸板率 (可选)
        """
        end_date = datetime.datetime.now()
        stats = []
        
        print(f"Analyzing market sentiment for the last {days} days...")
        
        for i in range(days):
            date_check = end_date - datetime.timedelta(days=i)
            date_str = date_check.strftime("%Y%m%d")
            
            # 跳过周末简单判断 (实际akshare会报错或返回空，这里做个预过滤更好)
            if date_check.weekday() > 4: 
                continue

            try:
                # 获取当日涨停池
                df_zt = ak.stock_zt_pool_em(date=date_str)
                if df_zt.empty: 
                    continue
                
                # 获取连板高度
                # 列名可能是 "连板数" 或 "lbc"
                col_lbc = '连板数' if '连板数' in df_zt.columns else 'lbc'
                max_height = df_zt[col_lbc].max() if not df_zt.empty else 0
                count = len(df_zt)
                
                stats.append({
                    'date': date_str,
                    'limit_up_count': count,
                    'max_height': int(max_height) if not pd.isna(max_height) else 0
                })
                
            except Exception as e:
                # 某些日期可能没数据（节假日），忽略
                continue
        
        # 按日期正序排列
        self.history_stats = sorted(stats, key=lambda x: x['date'])
        return self.history_stats

    def determine_phase(self):
        """
        根据最近的数据判定当前周期阶段
        """
        if not self.history_stats:
            return self.config.PHASE_DIVERGENCE # 默认分歧
            
        # 取最近3天的数据趋势
        recent = self.history_stats[-3:]
        if len(recent) < 2:
            return self.config.PHASE_DIVERGENCE

        latest = recent[-1]
        prev = recent[-2]
        
        height_curr = latest['max_height']
        height_prev = prev['max_height']
        
        count_curr = latest['limit_up_count']
        count_prev = prev['limit_up_count']

        # 1. 冰点判定
        if height_curr <= self.config.ICE_POINT_HEIGHT:
            return self.config.PHASE_ICE_POINT
            
        # 2. 上升期判定 (高度向上，且家数没有大幅减少)
        if height_curr > height_prev and count_curr >= count_prev * 0.8:
            return self.config.PHASE_RISING

        # 3. 退潮期判定 (高度显著下降)
        if height_curr < height_prev and height_curr < 5:
            return self.config.PHASE_DECLINE
            
        # 4. 其他情况归为分歧/震荡
        return self.config.PHASE_DIVERGENCE

    def get_strategy_suggestion(self):
        phase = self.determine_phase()
        if phase == self.config.PHASE_RISING:
            return "积极试错: 关注前排核心，大胆接力"
        elif phase == self.config.PHASE_ICE_POINT:
            return "冰点试错: 关注首板切低位，博弈新周期龙一"
        elif phase == self.config.PHASE_DECLINE:
            return "防守为主: 空仓或轻仓，严禁接力中位股"
        else:
            return "分歧震荡: 去弱留强，关注弱转强机会"

if __name__ == "__main__":
    engine = EmotionalCycleEngine()
    data = engine.fetch_market_mood(days=5)
    print("Recent Stats:", data)
    print("Current Phase:", engine.determine_phase())
    print("Suggestion:", engine.get_strategy_suggestion())
