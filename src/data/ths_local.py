# ==============================================================================
# 📂 同花顺本地数据解析器 (src/data/ths_local.py)
# 功能：解析同花顺导出的 TXT/Excel 表格数据 (如竞价表、涨停表)
# ==============================================================================

import os
import pandas as pd
import re
from colorama import Fore
from datetime import datetime


class THSLocalLoader:
    def __init__(self, base_dir):
        """
        :param base_dir: 数据存放根目录 (例如 data/input/call_auction)
        """
        self.base_dir = base_dir

    def load_auction_table(self, date_str: str = None) -> pd.DataFrame:
        """
        加载指定日期的同花顺竞价表格
        文件名格式支持: Table_20260206.txt 或 20260206.txt
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y%m%d')

        if not os.path.exists(self.base_dir):
            return pd.DataFrame()

        # 1. 寻找匹配的文件
        target_file = None
        for f in os.listdir(self.base_dir):
            if date_str in f and (f.endswith('.txt') or f.endswith('.xls')):
                target_file = os.path.join(self.base_dir, f)
                break

        if not target_file:
            # print(f"{Fore.YELLOW}⚠️ [本地] 未找到 {date_str} 的竞价文件 (路径: {self.base_dir})")
            return pd.DataFrame()

        print(f"{Fore.CYAN}📂 [本地] 加载竞价文件: {os.path.basename(target_file)}", end="")

        try:
            # 2. 读取文件 (自动尝试多种编码)
            # 同花顺导出通常是制表符分隔(\t)
            # 编码优先级: gb18030 (最全) > gbk (常见) > utf-8 > utf-16
            encodings_to_try = ['gb18030', 'gbk', 'utf-8', 'utf-16']
            df = None
            success_enc = ""

            for enc in encodings_to_try:
                try:
                    # on_bad_lines='skip' 防止文件末尾有奇怪的文字说明导致解析失败
                    df = pd.read_csv(target_file, sep='\t', encoding=enc, dtype={'代码': str}, on_bad_lines='skip')
                    success_enc = enc
                    break
                except UnicodeDecodeError:
                    continue
                except Exception:
                    continue

            if df is None:
                print(f" {Fore.RED}❌ 解码失败 (尝试了 {encodings_to_try})")
                return pd.DataFrame()

            # print(f" (编码:{success_enc})")

            # 3. 字段清洗与映射
            # 去除列名空格
            df.columns = [c.strip() for c in df.columns]

            # 必须包含的列 (兼容同花顺的不同导出模板)
            # 有时候叫 '早盘竞价金额'，有时候叫 '竞价金额'
            if '早盘竞价金额' not in df.columns and '竞价金额' in df.columns:
                df.rename(columns={'竞价金额': '早盘竞价金额'}, inplace=True)

            required_cols = ['代码', '名称', '早盘竞价金额', '竞价涨幅%']
            missing_cols = [c for c in required_cols if c not in df.columns]

            if missing_cols:
                print(f" {Fore.RED}❌ 格式不匹配，缺少列: {missing_cols}")
                return pd.DataFrame()

            # 数据清洗
            clean_data = []
            for _, row in df.iterrows():
                try:
                    raw_code = str(row['代码']).strip()
                    # 过滤掉非股票行 (有时候会有 '数据来源:同花顺' 这种尾行)
                    if not raw_code or not raw_code[0].isdigit() and not raw_code.startswith('S'):
                        continue

                    # 同花顺代码 SH600000 -> 600000.SH
                    ts_code = raw_code
                    if raw_code.startswith('SH'):
                        ts_code = raw_code[2:] + '.SH'
                    elif raw_code.startswith('SZ'):
                        ts_code = raw_code[2:] + '.SZ'
                    elif raw_code.startswith('BJ'):
                        ts_code = raw_code[2:] + '.BJ'
                    elif raw_code.startswith('6'):
                        ts_code = raw_code + '.SH'
                    elif raw_code.startswith('0') or raw_code.startswith('3'):
                        ts_code = raw_code + '.SZ'
                    elif raw_code.startswith('8') or raw_code.startswith('4'):
                        ts_code = raw_code + '.BJ'

                    # 竞价金额处理
                    raw_amt = row['早盘竞价金额']
                    auc_amt = self._parse_ths_number(raw_amt)

                    # 竞价涨幅处理
                    raw_pct = str(row['竞价涨幅%']).replace('%', '').replace('+', '').replace('--', '0')
                    try:
                        auc_pct = float(raw_pct)
                    except:
                        auc_pct = 0.0

                    clean_data.append({
                        'ts_code': ts_code,
                        'code': ts_code.split('.')[0],
                        'name': str(row['名称']).strip(),
                        'auc_amt': auc_amt,
                        'auc_pct': auc_pct,
                        'is_local_source': True
                    })
                except Exception:
                    continue

            return pd.DataFrame(clean_data)

        except Exception as e:
            print(f" {Fore.RED}❌ 解析异常: {e}")
            return pd.DataFrame()

    def _parse_ths_number(self, val):
        """解析同花顺的数字格式 (如 1.23亿, 500万, 12345)"""
        if pd.isna(val) or val == '--': return 0.0
        val = str(val).strip()

        multi = 1
        if '亿' in val:
            multi = 100000000
            val = val.replace('亿', '')
        elif '万' in val:
            multi = 10000
            val = val.replace('万', '')

        try:
            return float(val) * multi
        except:
            return 0.0