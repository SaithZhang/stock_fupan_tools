# ==============================================================================
# 🚀 实时数据驱动 (src/data/realtime.py)
# Version: 3.8 (修复版)
# 核心功能：
# 1. 强制绕过代理 (解决 VPN 导致的连接错误)
# 2. 提供 get_realtime_data 适配器 (解决 AttributeError)
# 3. 自动处理 sh/sz 前缀与去前缀逻辑
# ==============================================================================

import os
import requests
import re
from concurrent.futures import ThreadPoolExecutor

# --- 🟢 核心设置：强制让本脚本“无视”梯子，直连国内接口 ---
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'


class TencentRealtime:
    """腾讯实时行情接口"""

    BASE_URL = "http://qt.gtimg.cn/q="

    def get_realtime_data(self, codes):
        """
        [适配器方法] 供 call_auction_screener.py 调用
        功能：自动为纯数字代码添加 sh/sz 前缀，然后获取数据
        """
        if not codes: return {}

        fixed_codes = []
        for code in codes:
            code_str = str(code).strip()
            # 如果已经是 sh/sz 开头，直接用
            if code_str.startswith(('sh', 'sz')):
                fixed_codes.append(code_str)
            # 否则根据首位数字补全前缀
            elif code_str.startswith('6'):
                fixed_codes.append(f"sh{code_str}")
            elif code_str.startswith(('0', '3')):
                fixed_codes.append(f"sz{code_str}")
            elif code_str.startswith(('4', '8')):  # 北交所
                fixed_codes.append(f"bj{code_str}")
            else:
                # 其他情况直接放入，碰运气
                fixed_codes.append(code_str)

        # 调用底层批量接口
        return self.get_batch_quotes(fixed_codes)

    def get_batch_quotes(self, codes):
        """
        批量获取个股实时行情 (底层核心)
        返回字典结构: {code: {name, price, pct, amount, ...}}
        注意：返回的 code 字典 key 会自动去除 sh/sz 前缀，以便与策略池匹配
        """
        if not codes: return {}

        # 分批请求，防止 URL 过长 (腾讯接口限制)
        chunk_size = 60
        chunks = [codes[i:i + chunk_size] for i in range(0, len(codes), chunk_size)]

        results = {}

        def fetch_chunk(chunk):
            try:
                url = self.BASE_URL + ",".join(chunk)
                # 设置超时，防止卡死
                res = requests.get(url, timeout=3)
                # 腾讯接口通常是 gbk 编码
                res.encoding = 'gbk'
                return self._parse_tencent_data(res.text)
            except Exception as e:
                # 生产环境可以选择不打印报错，或者打印到日志
                # print(f"❌ Batch Error: {e}")
                return {}

        # 多线程并发抓取
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_chunk, chunk) for chunk in chunks]
            for future in futures:
                try:
                    data = future.result()
                    if data:
                        results.update(data)
                except:
                    pass
        return results

    def _parse_tencent_data(self, text):
        """解析腾讯返回的原始字符串"""
        data = {}
        # 正则提取：v_sh600000="1~名称~..."
        pattern = re.compile(r'v_([a-z0-9]+)="([^"]+)"')
        items = pattern.findall(text)

        for code_with_prefix, content in items:
            parts = content.split('~')
            # 数据字段不足，跳过
            if len(parts) < 45: continue

            try:
                # --- 核心：去除前缀 (sh600000 -> 600000) ---
                # 这样才能和 strategy_pool.csv 里的纯数字 ID 对应上
                clean_code = code_with_prefix[2:] if code_with_prefix.startswith(
                    ('sh', 'sz', 'bj')) else code_with_prefix

                name = parts[1]
                price = float(parts[3])
                pre_close = float(parts[4])
                open_price = float(parts[5])

                # 腾讯接口：成交量(手)，成交额(万)
                # 我们统一转为标准单位：量(手)，额(元)
                amount_wan = float(parts[37]) if parts[37] else 0.0
                amount = amount_wan * 10000

                pct = float(parts[32]) if parts[32] else 0.0

                # 涨跌停价 (可选，辅助判断炸板)
                limit_up = float(parts[47]) if len(parts) > 47 else 0.0
                limit_down = float(parts[48]) if len(parts) > 48 else 0.0

                data[clean_code] = {
                    'name': name,
                    'price': price,
                    'pre_close': pre_close,
                    'open': open_price,
                    'pct': pct,
                    'amount': amount,
                    'limit_up': limit_up,
                    'limit_down': limit_down
                }
            except:
                continue
        return data


class EastMoneyBlock:
    """东方财富板块/大盘接口 (保留原功能)"""

    def fetch_all_sectors(self):
        """拉取东财板块涨幅"""
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": 1, "pz": 200, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3", "fs": "m:90 t:2 f:!50",
                "fields": "f12,f14,f3"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://quote.eastmoney.com/center/gridlist.html"
            }
            res = requests.get(url, params=params, headers=headers, timeout=5)
            if res.status_code != 200: return []

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
        except:
            return []