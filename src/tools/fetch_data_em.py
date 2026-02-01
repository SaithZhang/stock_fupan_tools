# src/tools/fetch_daily_data_em.py
import requests
import pandas as pd
import os
import sys
import datetime
import json

# 解决 Windows 控制台乱码
sys.stdout.reconfigure(encoding='utf-8')

# ================= 配置区 =================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'input', 'ths')  # 保持原有路径习惯
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

TODAY_STR = datetime.datetime.now().strftime('%Y%m%d')


# ================= 核心函数 =================

def get_all_stock_realtime():
    """
    获取全市场实时行情（东方财富接口）
    包含：代码、名称、最新价、涨跌幅、成交额、换手率、量比、主力净流、市盈率、流通市值
    """
    print("⏳ 正在请求全市场行情数据 (东方财富)...")
    url = "http://82.push2.eastmoney.com/api/qt/clist/get"

    # fs 参数解释: m:0+t:6,m:0+t:80 (沪深A股)
    # fields 参数映射: f12=代码, f14=名称, f2=最新价, f3=涨幅, f4=涨跌额, f5=成交量, f6=成交额
    # f8=换手率, f9=市盈率, f10=量比, f20=流通市值, f62=主力净流入, f100=所属行业
    params = {
        "pn": 1,
        "pz": 10000,  # 一次拉取所有股票
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # 沪深A股
        "fields": "f12,f14,f2,f3,f6,f8,f10,f62,f100,f20",
        "_": "1626057000000"
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data['data'] and data['data']['diff']:
            df = pd.DataFrame(data['data']['diff'])

            # 重命名列以匹配你之前的习惯
            rename_map = {
                'f12': '代码',
                'f14': '名称',
                'f2': '最新价',
                'f3': '涨幅',
                'f6': '成交额',
                'f8': '换手率',
                'f10': '量比',
                'f62': '主力资金',
                'f100': '所属行业',  # 注意：东财的行业通常是板块名，这里是简单的分类
                'f20': '流通市值'
            }
            df.rename(columns=rename_map, inplace=True)

            # 数据清洗
            df = df[df['最新价'] != '-']  # 去除无数据
            # 转换数值类型
            cols = ['最新价', '涨幅', '成交额', '换手率', '主力资金', '流通市值']
            for c in cols:
                df[c] = pd.to_numeric(df[c], errors='coerce')

            return df
        else:
            print("❌ 获取行情数据为空")
            return None
    except Exception as e:
        print(f"❌ 请求行情接口失败: {e}")
        return None


def get_limit_up_pool():
    """
    获取涨停池数据（包含连板天数、涨停原因）
    """
    print("⏳ 正在请求涨停分析数据...")
    # 东方财富涨停池接口
    url = "http://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztgc",
        "Pageindex": 0,
        "pagesize": 1000,  # 足够涵盖当日所有涨停
        "sort": "fbt:asc",
        "date": TODAY_STR,  # 如果是盘后跑，用当天日期；如果是盘中，自动取最新
        "_": "1626057000000"
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and 'data' in data and 'pool' in data['data']:
                df = pd.DataFrame(data['data']['pool'])
                # 提取需要的字段
                # c: 代码, n: 名称, lbc: 连板数, hybk: 行业板块, zttj: 涨停统计(几板), reason: 涨停原因
                df = df[['c', 'lbc', 'hybk', 'expl']]
                df.rename(columns={
                    'c': '代码',
                    'lbc': '连续涨停天数',
                    'hybk': '东财行业',
                    'expl': '涨停原因类别'
                }, inplace=True)
                return df
    except Exception as e:
        print(f"⚠️ 获取涨停数据失败 (可能是非交易时间或接口变动): {e}")

    return pd.DataFrame()  # 失败返回空DF


def filter_data(df):
    """
    执行过滤：非ST、非北交所
    """
    print("🧹 执行数据清洗 (去ST, 去北交所)...")

    # 1. 过滤北交所 (代码以 8 或 4 开头，或 920 开头)
    # 东财代码通常是6位字符串
    df = df[~df['代码'].str.startswith(('8', '4', '92'))]

    # 2. 过滤ST
    df = df[~df['名称'].str.contains('ST')]

    return df


def main():
    print(f"🚀 [{datetime.datetime.now()}] 启动全市场数据拉取 (Direct Mode)...")

    # 1. 获取基础行情
    df_market = get_all_stock_realtime()
    if df_market is None:
        return

    # 2. 获取涨停详细数据 (为了补全 '连续涨停天数' 和 '涨停原因')
    df_zt = get_limit_up_pool()

    # 3. 合并数据
    if not df_zt.empty:
        # 东财代码可能不带市场后缀，确保格式一致
        # 行情接口返回的是 6位代码，涨停接口也是 6位，直接 merge
        df_final = pd.merge(df_market, df_zt, on='代码', how='left')

        # 填充 NaN
        df_final['连续涨停天数'] = df_final['连续涨停天数'].fillna(0).astype(int)
        df_final['涨停原因类别'] = df_final['涨停原因类别'].fillna('')
    else:
        df_final = df_market
        df_final['连续涨停天数'] = 0
        df_final['涨停原因类别'] = ''

    # 4. 过滤 (模拟问句中的 "非ST, 非北交所")
    df_final = filter_data(df_final)

    # 5. 计算/调整列
    # 东财的成交额单位通常是元，有时需要转为 亿/万，这里保持原始值或按需除
    # 问财的 "几天几板" 比较特殊，这里用 "连续涨停天数" 代替，或者自己写逻辑计算

    # 6. 排序 (按涨幅降序)
    df_final.sort_values(by='涨幅', ascending=False, inplace=True)

    print(f"✅ 拉取并清洗成功！获取数据: {len(df_final)} 条")

    # 7. 保存
    file_name = f"Table-{TODAY_STR}.csv"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    # 选取你关心的列
    out_cols = [
        '代码', '名称', '最新价', '涨幅', '成交额', '换手率',
        '主力资金', '所属行业', '连续涨停天数', '涨停原因类别', '流通市值'
    ]
    # 确保列存在
    out_cols = [c for c in out_cols if c in df_final.columns]

    df_final[out_cols].to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"💾 文件已保存: {file_path}")

    # 验证打印
    print("-" * 30)
    print(df_final[out_cols].head(5))
    print("-" * 30)


if __name__ == "__main__":
    main()