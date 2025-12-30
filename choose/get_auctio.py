import requests
import time
import os

# ==========================================
# 监控列表 (已包含你的持仓 + F佬核心 + 避雷针)
# ==========================================
STOCKS = [
    # --- 你的持仓 ---
    "sh600755",  # 厦门国贸
    "sz002703",  # 浙江世宝
    "sz001231",  # 农心科技
    "sz300115",  # 长盈精密
    "sh603667",  # 五洲新春
    "sh600592",  # 龙溪股份

    # --- 核心风向标 ---
    "sh600179",  # 安通控股 (空间龙)
    "sz300757",  # 罗博特科 (机器人强度)
    "sh688270",  # 臻镭科技 (核按钮强度)
    "sz002361",  # 神剑股份 (异动雷)
    "sh600118",  # 中国卫星 (航天中军)
    "sh600693",  # 东百集团 (消费补涨)
]


def get_data():
    url = f"http://hq.sinajs.cn/list={','.join(STOCKS)}"
    headers = {'Referer': 'https://finance.sina.com.cn'}

    try:
        resp = requests.get(url, headers=headers, timeout=3)
        # 强制设置编码，防止Windows下出现乱码
        resp.encoding = 'gbk'
        text = resp.text

        # 清屏 (Windows用cls, Mac/Linux用clear)
        os.system('cls' if os.name == 'nt' else 'clear')

        print("=" * 50)
        print(f"🔥 竞价实战监控 | 时间: {time.strftime('%H:%M:%S')}")
        print("=" * 50)
        print(f"{'名称':<8}\t{'涨幅':<8}\t{'现价':<8}\t{'量(手)':<8}")
        print("-" * 50)

        output_data = []  # 用于复制的纯文本列表

        lines = text.strip().split('\n')
        for line in lines:
            if not line: continue
            try:
                # 解析新浪数据
                # var hq_str_sh600755="厦门国贸,open,pre_close,price,high,low,buy,sell,vol,amount,..."
                data_part = line.split('=')[1].strip('"')
                if not data_part: continue

                data = data_part.split(',')
                name = data[0]
                open_price = float(data[1])  # 9:15-9:25期间，这就是竞价价格
                pre_close = float(data[2])  # 昨收

                # 9:25之前有些票可能暂时没开出价格，open会是0.0
                if open_price == 0:
                    price_str = "未开"
                    pct_str = "0.00%"
                else:
                    pct = (open_price - pre_close) / pre_close * 100
                    pct_str = f"{pct:+.2f}%"
                    price_str = f"{open_price:.2f}"

                # 成交量 (股 -> 手)
                vol = int(data[8]) // 100

                # 打印到屏幕 (方便你看)
                print(f"{name:<8}\t{pct_str:<8}\t{price_str:<8}\t{vol}")

                # 存一个纯文本格式 (方便你复制发给我)
                output_data.append(f"{name} {pct_str} {price_str} 量:{vol}")

            except Exception:
                continue

        print("=" * 50)
        print("👉 9:25:01 时，鼠标选中上面数据 -> 右键复制 -> 发给我")
        print("👉 按 Ctrl+C 停止刷新")

    except Exception as e:
        print(f"网络请求错误: {e}")


if __name__ == "__main__":
    print("🚀 监控脚本启动... (按 Ctrl+C 退出)")
    try:
        while True:
            get_data()
            # 9:15-9:20 可以5秒刷一次，9:24开始最好2秒刷一次
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n🛑 监控已停止")