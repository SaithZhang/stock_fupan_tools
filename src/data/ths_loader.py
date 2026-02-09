# ==============================================================================
# 📈 同花顺数据加载器 (src/data/ths_loader.py)
# 功能：专门对接 Tushare 的同花顺(THS) 涨跌停接口
# ==============================================================================

import pandas as pd
from time import sleep
from colorama import Fore


class ThsDataLoader:
    def __init__(self, pro_client):
        """
        :param pro_client: 已经初始化好的 tushare pro 客户端
        """
        self.pro = pro_client

    def get_market_limit_stats(self, date_str: str):
        """
        获取指定日期的涨跌停统计数据（权威榜单）
        :param date_str: 格式 YYYYMMDD
        :return: (stats_dict, limit_up_df, limit_down_df)
        """
        print(f"{Fore.CYAN}🔍 [ThsLoader] 正在请求同花顺涨跌停榜单 ({date_str})...")

        # 1. 获取涨停池
        try:
            df_up = self.pro.limit_list_ths(trade_date=date_str, limit_type='涨停池')
        except Exception as e:
            print(f"{Fore.RED}❌ 获取涨停池失败: {e}")
            df_up = pd.DataFrame()

        # 避免接口流控，稍作停顿
        sleep(0.3)

        # 2. 获取跌停池
        try:
            df_down = self.pro.limit_list_ths(trade_date=date_str, limit_type='跌停池')
        except Exception as e:
            print(f"{Fore.RED}❌ 获取跌停池失败: {e}")
            df_down = pd.DataFrame()

        # 3. 统计数据
        count_up = len(df_up) if not df_up.empty else 0
        count_down = len(df_down) if not df_down.empty else 0

        # 4. 获取连板高度 (如果不为空)
        height = 0
        if count_up > 0 and 'status' in df_up.columns:
            # 提取 "3连板", "2连板" 中的数字
            # 假设 status 格式为 "N连板" 或 "首板"
            try:
                # 过滤出含有'连板'的，提取数字，取最大值
                lb_series = df_up['status'].astype(str)

                # 简单的逻辑：提取数字，首板算1
                def parse_height(s):
                    if '连板' in s:
                        return int(''.join(filter(str.isdigit, s)) or 0)
                    return 1

                height = lb_series.apply(parse_height).max()
            except:
                height = 0

        print(f"   🔥 权威校准: 涨停 {count_up} 家 | 跌停 {count_down} 家 | 最高板 {height}")

        stats_override = {
            'limit_up_count': count_up,
            'limit_down_count': count_down,
            'highest_plate': height
        }

        return stats_override, df_up, df_down