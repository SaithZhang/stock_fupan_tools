# ==============================================================================
# 📡 实时数据接口 (src/data/realtime.py)
# Version: 3.6 (Proxy Bypass + Akshare)
# 修复：
# 1. 强制禁用 Python 脚本的代理，允许用户开梯子的同时直连国内接口
# 2. 优先使用 Akshare，失败则回退到备用接口
# ==============================================================================

import os
import requests
import pandas as pd
from colorama import Fore, Style
from typing import List, Dict, Optional

# --- 🟢 核心修复：强制让本脚本“无视”梯子 ---
# 这样你开着全局代理也能跑国内爬虫，不会报 ProxyError
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# 尝试导入 akshare，如果没有安装则降级处理
try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


class TencentRealtime:
    """
    腾讯财经实时行情获取器 (个股/指数)
    """
    BASE_URL = "http://qt.gtimg.cn/q="

    @staticmethod
    def fetch_quotes(code_list: List[str]) -> pd.DataFrame:
        if not code_list: return pd.DataFrame()

        chunk_size = 60
        all_data = []

        # 腾讯接口通常不需要特殊 Header，但为了保险，给一个基本的
        headers = {"User-Agent": "Mozilla/5.0"}

        for i in range(0, len(code_list), chunk_size):
            chunk = code_list[i:i + chunk_size]
            url = TencentRealtime.BASE_URL + ",".join(chunk)

            try:
                # proxies=None 是双重保险，确保不走代理
                resp = requests.get(url, headers=headers, timeout=2.0, proxies=None)
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
            except Exception:
                pass

        return pd.DataFrame(all_data)

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        try:
            var_name, content = line.split('="')
            code = var_name.split('_')[-1]
            parts = content.strip('"').split('~')

            if len(parts) < 49: return None

            pre_close = float(parts[4])
            current_price = float(parts[3])
            open_price = float(parts[5])
            price = current_price if current_price > 0 else (open_price if open_price > 0 else pre_close)

            pct = 0.0
            if pre_close > 0:
                pct = (price - pre_close) / pre_close * 100

            return {
                'sina_code': code,
                'name': parts[1],
                'price': price,
                'pct': pct,
                'amount': float(parts[37]) * 10000 if parts[37] else 0,
                'turnover': float(parts[38]) if parts[38] else 0.0,
                'vol_ratio': float(parts[49]) if parts[49] else 0.0,
                'mv_yi': float(parts[45]) if parts[45] else 0,
                'limit_up': float(parts[47]),
                'limit_down': float(parts[48])
            }
        except Exception:
            return None


class EastMoneyBlock:
    """
    东方财富板块数据获取器 (Akshare 封装版)
    """

    @staticmethod
    def fetch_all_sectors() -> List[Dict]:
        """
        获取行业板块涨跌幅
        """
        # 1. 优先使用 Akshare (因为有了 os.environ['NO_PROXY']，这里应该能通了)
        if HAS_AKSHARE:
            try:
                # 获取东方财富行业板块实时行情
                df = ak.stock_board_industry_name_em()
                result = []
                for _, row in df.iterrows():
                    result.append({
                        'code': str(row.get('板块代码')),
                        'name': str(row.get('板块名称')),
                        'pct': float(row.get('涨跌幅'))
                    })
                return result
            except Exception as e:
                # Akshare 可能会因为东财改版而临时失效，如果失败则静默进入方案2
                pass

        # 2. 备用纯净接口 (Requests)
        try:
            url = "http://82.push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1, "pz": 200, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90 t:2 f:!50",
                "fields": "f12,f14,f3"
            }
            # 必须带 Header，否则 503
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://quote.eastmoney.com/center/gridlist.html"
            }
            # proxies=None 是三重保险
            res = requests.get(url, params=params, headers=headers, timeout=3.0, proxies=None)

            data = res.json()
            result = []
            if data and data.get('data'):
                for item in data['data']['diff']:
                    if item.get('f3') is None: continue
                    result.append({
                        'code': item.get('f12'),
                        'name': item.get('f14'),
                        'pct': float(item['f3'])
                    })
            return result
        except Exception as e:
            # 如果两个都失败了，这里会打印日志，但为了不刷屏主监控，返回空列表
            # print(f"Error: {e}")
            return []