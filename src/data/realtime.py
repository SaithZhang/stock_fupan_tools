# ==============================================================================
# 🚀 实时数据驱动 (src/data/realtime.py)
# Version: 3.7 (兼容版)
# 核心功能：
# 1. 强制绕过代理 (解决 VPN 导致的连接错误)
# 2. 统一提供 get_batch_quotes 方法 (解决 AttributeError)
# 3. 集成东方财富板块接口 (解决盘中雷达报错)
# ==============================================================================

import os
import requests
import re
from concurrent.futures import ThreadPoolExecutor

# --- 🟢 核心修复：强制让本脚本“无视”梯子，直连国内接口 ---
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'


class TencentRealtime:
    """腾讯实时行情接口"""

    BASE_URL = "http://qt.gtimg.cn/q="

    def get_batch_quotes(self, codes):
        """
        批量获取个股实时行情 (监控脚本专用接口)
        返回字典结构: {code: {name, price, pct, turnover, amount, vr...}}
        """
        if not codes: return {}

        # 分批请求，防止 URL 过长
        chunk_size = 80
        # 过滤非法代码
        valid_codes = [c for c in codes if isinstance(c, str) and (c.startswith('sz') or c.startswith('sh'))]
        chunks = [valid_codes[i:i + chunk_size] for i in range(0, len(valid_codes), chunk_size)]

        results = {}

        def fetch_chunk(chunk):
            try:
                url = self.BASE_URL + ",".join(chunk)
                res = requests.get(url, timeout=3)
                res.encoding = 'gbk'
                return self._parse_tencent_data(res.text)
            except:
                return {}

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_chunk, chunk) for chunk in chunks]
            for future in futures:
                try:
                    results.update(future.result())
                except:
                    pass
        return results

    def _parse_tencent_data(self, text):
        data = {}
        # 正则提取数据
        pattern = re.compile(r'v_([a-z0-9]+)="(.*?)";')
        items = pattern.findall(text)

        for code, content in items:
            parts = content.split('~')
            if len(parts) < 45: continue

            try:
                name = parts[1]
                price = float(parts[3])
                pre_close = float(parts[4])
                open_price = float(parts[5])
                volume = float(parts[6])

                # 量比 (索引49)
                vr = float(parts[49]) if len(parts) > 49 and parts[49] else 0.0

                # 成交额 (单位转为元)
                amount = float(parts[37]) * 10000
                turnover = float(parts[38]) if parts[38] else 0.0
                pct = float(parts[32]) if parts[32] else 0.0

                # 涨跌停价 (用于判断炸板)
                limit_up = float(parts[47]) if len(parts) > 47 else 0.0
                limit_down = float(parts[48]) if len(parts) > 48 else 0.0

                data[code] = {
                    'name': name, 'price': price, 'pre_close': pre_close,
                    'open': open_price, 'pct': pct, 'volume': volume,
                    'amount': amount, 'turnover': turnover, 'vr': vr,
                    'limit_up': limit_up, 'limit_down': limit_down
                }
            except:
                continue
        return data


class EastMoneyBlock:
    """东方财富板块/大盘接口"""

    def get_market_snapshot(self):
        """获取大盘指数 + 领涨/领跌板块"""
        snapshot = {'indexes': {}, 'hot_blocks': [], 'cold_blocks': []}

        # 1. 获取核心指数 (借用腾讯接口)
        index_codes = ['sh000001', 'sz399001', 'sz399006', 'sh000688']
        tc = TencentRealtime()
        idx_data = tc.get_batch_quotes(index_codes)

        name_map = {'sh000001': '上证', 'sz399001': '深证', 'sz399006': '创业', 'sh000688': '科创'}

        for code, info in idx_data.items():
            short_name = name_map.get(code, info['name'])
            snapshot['indexes'][short_name] = info['pct']

        # 2. 获取行业板块
        sectors = self.fetch_all_sectors()
        if sectors:
            sectors.sort(key=lambda x: x['pct'], reverse=True)
            snapshot['hot_blocks'] = sectors[:5]
            snapshot['cold_blocks'] = sectors[-5:][::-1]

        return snapshot

    def fetch_all_sectors(self):
        """拉取东财板块涨幅 (增强调试版)"""
        try:
            # 接口地址
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1, "pz": 200, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90 t:2 f:!50",
                "fields": "f12,f14,f3"
            }
            # 完善请求头
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://quote.eastmoney.com/center/gridlist.html"
            }

            # 1. 增加超时时间到 5秒
            res = requests.get(url, params=params, headers=headers, timeout=5)

            if res.status_code != 200:
                print(f"❌ 东财接口状态码异常: {res.status_code}")
                return []

            data = res.json()
            result = []
            if data and data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    result.append({
                        'code': item['f12'],
                        'name': item['f14'],
                        'pct': item['f3']
                    })
            return result

        except Exception as e:
            # 2. 打印具体错误，不再静默失败
            # 引入 colorama 需要在文件头 import，或者直接用 print
            print(f"❌ 板块数据获取失败: {e}")
            return []