# src/tools/fetch_daily_data_hybrid.py
import time
import json
import pandas as pd
import os
import datetime
import sys
import re
import requests
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# 解决控制台乱码
sys.stdout.reconfigure(encoding='utf-8')

# ================= 配置区 =================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

TODAY_STR = datetime.datetime.now().strftime('%Y%m%d')


def clean_code(code_str):
    return re.sub(r'\D', '', str(code_str)).zfill(6)


def get_cookie_via_browser():
    """启动浏览器，访问一次问财，获取“新鲜热乎”的 Cookie"""
    print(f"🚀 [{datetime.datetime.now()}] 启动 Edge 浏览器获取授权...")

    edge_options = Options()
    # ⚠️ 关键：建议先不开启 headless，让你看到浏览器真的打开了，方便排查
    # 稳定后可以把下面这行取消注释
    # edge_options.add_argument('--headless')
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=edge_options)

    try:
        # 1. 访问问财首页，触发 Cookie 生成
        driver.get("http://www.iwencai.com/unifiedwap/result?w=A股&querytype=stock")

        # 2. 等待几秒，确保 hexin-v 生成
        print("⏳ 等待页面加载和 Token 生成 (5秒)...")
        time.sleep(5)

        # 3. 偷取 Cookies
        selenium_cookies = driver.get_cookies()

        # 4. 拼装成 Requests 可用的格式
        cookie_dict = {}
        cookie_str = ""
        for item in selenium_cookies:
            cookie_dict[item['name']] = item['value']
            cookie_str += f"{item['name']}={item['value']}; "

        print(f"✅ 成功获取 Cookie! (hexin-v 存在: {'hexin-v' in cookie_dict or 'v' in cookie_dict})")
        return cookie_str, cookie_dict['v'] if 'v' in cookie_dict else cookie_dict.get('hexin-v', '')

    except Exception as e:
        print(f"❌ 浏览器启动失败: {e}")
        return None, None
    finally:
        driver.quit()


def fetch_all_data(cookie_str, hexin_v):
    print("📡 开始通过 HTTP 接口高速拉取全量数据...")

    # 同花顺统一 API
    url = "http://www.iwencai.com/unifiedwap/unified-wap/v2/result/get-robot-data"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie_str,
        "hexin-v": hexin_v
    }

    # 你的完整查询
    query = "非ST, 非北交所, 股票代码, 股票简称, 最新价, 涨跌幅, 成交额, 换手率, 量比, 主力资金流向, 所属同花顺行业, 所属概念, 连续涨停天数, 几天几板, 涨停原因类别, 最终涨停时间, 首次涨停时间, 开板次数, 10日涨幅, 20日涨幅, 竞价涨幅, 竞价金额, 流通市值"

    all_datas = []
    page = 1

    while True:
        # 构造表单数据
        data = {
            "question": query,
            "perpage": 100,  # 每页100条
            "page": page,
            "secondary_intent": "stock",
            "log_info": "{\"source\":\"pc\"}",
            "source": "Ths_iwencai_Xuangu",
            "version": "2.0",
            "query_area": "",
            "block_list": "",
            "add_info": "{\"urp\":{\"scene\":1,\"company\":1,\"business\":1},\"contentType\":\"json\",\"searchInfo\":true}"
        }

        try:
            resp = requests.post(url, headers=headers, data=data, timeout=10)
            if resp.status_code != 200:
                print(f"❌ 请求失败: {resp.status_code}")
                break

            res_json = resp.json()

            # 深度解析 JSON 结构
            try:
                # 尝试不同的路径，增强健壮性
                answer = res_json['data']['answer'][0]['txt'][0]['content']['components'][0]['data']
                datas = answer['datas']
            except:
                if page == 1:
                    print("❌ 解析失败，可能 Cookie 失效或 IP 被封。")
                    # print(res_json) # 调试用
                break

            if not datas:
                break

            count = len(datas)
            print(f"   -> 第 {page} 页: 拉取 {count} 条")
            all_datas.extend(datas)

            if count < 100:  # 最后一页
                break

            page += 1
            time.sleep(0.3)  # 稍微温柔点

        except Exception as e:
            print(f"❌ 网络请求异常: {e}")
            break

    return all_datas


def main():
    # 1. 启动浏览器拿 Cookie
    cookie_str, hexin_v = get_cookie_via_browser()
    if not cookie_str:
        return

    # 2. 使用 Requests 批量拉取
    raw_data = fetch_all_data(cookie_str, hexin_v)

    if not raw_data:
        print("❌ 未获取到数据。")
        return

    print(f"\n📊 共获取 {len(raw_data)} 条数据，开始清洗...")
    df = pd.DataFrame(raw_data)

    # 3. 列名清洗 (直接复用你之前的逻辑)
    mapping_rules = {
        '代码': ['股票代码', 'code'],
        '名称': ['股票简称', '名称'],
        '现价': ['最新价', '收盘价', '现价'],
        '涨幅': ['涨跌幅', '涨幅'],
        '当日成交额': ['成交额'],
        '换手': ['换手率'],
        '主力净额': ['主力资金流向', '主力资金', 'dde'],
        '所属行业': ['所属同花顺行业', '所属行业'],
        '所属概念': ['所属概念'],
        '流通市值': ['流通市值', 'a股市值'],
        '连续涨停天数': ['连续涨停'],
        '几天几板': ['几天几板'],
        '涨停原因类别': ['涨停原因'],
        '竞价涨幅%': ['竞价涨幅'],
        '早盘竞价金额': ['竞价金额']
    }

    new_columns = {}
    used_cols = set()
    for target, keywords in mapping_rules.items():
        for col in df.columns:
            if col in used_cols: continue
            for kw in keywords:
                if kw in col:
                    new_columns[col] = target
                    used_cols.add(col)
                    break
            if col in used_cols: break

    df.rename(columns=new_columns, inplace=True)

    if '代码' in df.columns:
        df['代码'] = df['代码'].apply(clean_code)

    # 补全
    for col in ['代码', '名称', '所属行业', '涨幅']:
        if col not in df.columns: df[col] = ''

    # 4. 保存
    file_path = os.path.join(OUTPUT_DIR, f"Table-{TODAY_STR}.csv")

    if '涨幅' in df.columns:
        try:
            df['_s'] = pd.to_numeric(df['涨幅'], errors='coerce')
            df.sort_values(by='_s', ascending=False, inplace=True)
            df.drop(columns=['_s'], inplace=True)
        except:
            pass

    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"💾 完美！全量数据已保存至: {file_path}")
    print(df[['代码', '名称', '所属行业', '涨幅']].head())


if __name__ == "__main__":
    main()