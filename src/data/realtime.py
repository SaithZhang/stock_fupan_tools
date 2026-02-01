# ==============================================================================
# 📡 实时数据接口 (src/data/realtime.py)
# Version: 3.1 (Stable)
# 修复：补回 mv_yi 字段，兼容竞价和盘中监控
# ==============================================================================

import requests
import pandas as pd
from colorama import Fore
from typing import List, Dict, Optional


class TencentRealtime:
    """
    腾讯财经实时行情获取器
    """
    BASE_URL = "http://qt.gtimg.cn/q="

    @staticmethod
    def fetch_quotes(code_list: List[str]) -> pd.DataFrame:
        """批量获取行情，返回 DataFrame"""
        if not code_list: return pd.DataFrame()

        chunk_size = 60
        all_data = []

        for i in range(0, len(code_list), chunk_size):
            chunk = code_list[i:i + chunk_size]
            url = TencentRealtime.BASE_URL + ",".join(chunk)

            try:
                resp = requests.get(url, timeout=1.5)
                if resp.status_code != 200: continue

                lines = resp.text.split(';')
                for line in lines:
                    line = line.strip()
                    if not line or '="' not in line: continue

                    try:
                        parsed = TencentRealtime._parse_line(line)
                        if parsed: all_data.append(parsed)
                    except Exception:
                        continue
            except Exception as e:
                if i == 0: print(f"{Fore.RED}⚠️ 网络请求异常: {e}")

        return pd.DataFrame(all_data)

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        """
        解析单行数据
        [1]名称 [3]现价 [4]昨收 [5]开盘
        [37]成交额(万) [38]换手% [45]总市值(亿)
        [47]涨停 [48]跌停 [49]量比
        """
        try:
            var_name, content = line.split('="')
            code = var_name.split('_')[-1]
            parts = content.strip('"').split('~')

            if len(parts) < 49: return None

            pre_close = float(parts[4])
            current_price = float(parts[3])
            open_price = float(parts[5])

            # 价格兜底：如果盘中价为0，尝试用开盘价，再不行用昨收
            price = current_price if current_price > 0 else (open_price if open_price > 0 else pre_close)

            pct = 0.0
            if pre_close > 0:
                pct = (price - pre_close) / pre_close * 100

            amount_wan = float(parts[37]) if parts[37] else 0
            turnover = float(parts[38]) if parts[38] else 0.0
            vol_ratio = float(parts[49]) if parts[49] else 0.0
            total_mv = float(parts[45]) if parts[45] else 0  # <--- 关键修复：确保解析市值
            limit_up = float(parts[47])
            limit_down = float(parts[48])

            return {
                'sina_code': code,
                'name': parts[1],
                'price': price,
                'pct': pct,
                'amount': amount_wan * 10000,
                'turnover': turnover,
                'vol_ratio': vol_ratio,
                'mv_yi': total_mv,  # <--- 关键修复：返回字段
                'limit_up': limit_up,
                'limit_down': limit_down
            }
        except Exception:
            return None