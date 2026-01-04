import requests
import akshare as ak
import pandas as pd
import time
import os
from datetime import datetime, timedelta

# ==========================================
# 1. 监控列表
# ==========================================
STOCKS = [
    # --- 持仓 ---
    "sh603667", "sh600592", "sz300115", "sz002703", "sh600755", "sz001231",
    # --- 航天 ---
    "sz000547", "sz002792", "sh603278", "sh600783", "sz002363", "sh605598", "sh688270", "sh600118",
    # --- 消费 ---
    "sh600693", "sh600865", "sz002788", "sh600998",
    # --- 其他核心 ---
    "sh600179", "sz002163", "sh603123", "sz300757", "sz002361"
]

# ==========================================
# 2. 核心数据预加载 (量能 + 监管涨幅)
# ==========================================
CORE_DATA = {}


def init_core_data():
    print(f"⏳ 正在计算 {len(STOCKS)} 只标的 [昨日量能] & [10日监管涨幅]... (约15秒)")

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=40)).strftime("%Y%m%d")  # 多取点算涨幅

    for stock_code in STOCKS:
        try:
            symbol = stock_code[2:]
            # 获取日线
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date,
                                    adjust="qfq")

            if not df.empty and len(df) > 10:
                last_row = df.iloc[-1]
                vol_yesterday = last_row['成交量']
                current_close = last_row['收盘']

                # 计算10日涨幅 (F佬逻辑)
                # 基准价是 T-10 的收盘价 (即倒数第11行)
                base_price_10 = df.iloc[-11]['收盘']
                pct_10 = (current_close - base_price_10) / base_price_10 * 100

                CORE_DATA[stock_code] = {
                    'yesterday_vol': vol_yesterday,
                    'pct_10_days': pct_10
                }
                # print(f"✅ {symbol}: 10日涨幅 {pct_10:.1f}%")
            else:
                CORE_DATA[stock_code] = {'yesterday_vol': 0, 'pct_10_days': 0}

        except Exception:
            CORE_DATA[stock_code] = {'yesterday_vol': 0, 'pct_10_days': 0}

    print("🎉 核心数据装载完毕！F佬+拨佬双策略启动！\n")
    time.sleep(1)


# ==========================================
# 3. 实时监控 (增加监管列)
# ==========================================
def get_realtime_data():
    url = f"http://hq.sinajs.cn/list={','.join(STOCKS)}"
    headers = {'Referer': 'https://finance.sina.com.cn'}

    try:
        resp = requests.get(url, headers=headers, timeout=3)
        resp.encoding = 'gbk'
        text = resp.text

        os.system('cls' if os.name == 'nt' else 'clear')

        print("=" * 95)
        print(f"🔥 F佬监管 + 拨佬竞价 | {time.strftime('%H:%M:%S')} | 红色为高危，绿色为安全")
        print("=" * 95)
        # 新增 [10日涨幅] 列
        header = f"{'名称':<8} {'涨幅':<8} {'现价':<8} {'竞价额':<9} {'爆量比':<9} {'10日涨幅':<10} {'综合状态'}"
        print(header)
        print("-" * 95)

        lines = text.strip().split('\n')
        for line in lines:
            if not line: continue
            try:
                code_part = line.split('=')[0]
                stock_code = code_part.split('_')[-1]
                data_part = line.split('=')[1].strip('"')
                if not data_part: continue

                data = data_part.split(',')
                name = data[0][:4]
                open_price = float(data[1])
                pre_close = float(data[2])
                current_vol = int(data[8]) // 100
                current_amt = float(data[9])

                # 价格处理
                if open_price == 0:
                    open_price = pre_close
                    pct = 0.0
                else:
                    pct = (open_price - pre_close) / pre_close * 100

                pct_str = f"{pct:+.2f}%"
                price_str = f"{open_price:.2f}"

                # 金额处理
                if current_amt > 100000000:
                    amt_str = f"{current_amt / 100000000:.1f}亿"
                else:
                    amt_str = f"{int(current_amt / 10000)}万"

                # --- 核心逻辑计算 ---
                static_data = CORE_DATA.get(stock_code, {})
                yesterday_vol = static_data.get('yesterday_vol', 0)
                pct_10 = static_data.get('pct_10_days', 0)

                # 1. 爆量比
                if yesterday_vol > 0:
                    ratio = (current_vol / yesterday_vol) * 100
                    ratio_str = f"{ratio:.1f}%"
                else:
                    ratio_str = "-"
                    ratio = 0

                # 2. 监管风险 (F佬)
                reg_status = ""
                if pct_10 > 90:
                    reg_str = f"⚠️{pct_10:.0f}%"  # 高危
                elif pct_10 > 70:
                    reg_str = f"⚡{pct_10:.0f}%"  # 警戒
                else:
                    reg_str = f"✅{pct_10:.0f}%"  # 安全

                # 3. 综合状态判定 (拨佬)
                status = ""
                # 逻辑A：监管高危 + 涨停预期 = 必炸/必断
                if pct_10 > 90 and pct > 5:
                    status = "🚫诱多(监管压顶)"
                # 逻辑B：安全 + 爆量 + 高开 = 弱转强
                elif pct_10 < 60 and ratio > 5 and pct > 0:
                    status = "🚀空间龙(可干)"
                # 逻辑C：核按钮
                elif pct < -4:
                    status = "🤮核按钮"
                # 逻辑D：普通爆量
                elif ratio > 5:
                    status = "🔥抢筹"

                print(f"{name:<8} {pct_str:<8} {price_str:<8} {amt_str:<9} {ratio_str:<9} {reg_str:<10} {status}")

            except Exception:
                continue
        print("=" * 95)
        print("👉 重点找：[10日涨幅]显示✅ 且 [爆量比]>5% 的红色代码！")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    init_core_data()
    print("🚀 监控中... (Ctrl+C 停止)")
    try:
        while True:
            get_realtime_data()
            time.sleep(3)
    except KeyboardInterrupt:
        print("Done.")