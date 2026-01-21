import akshare as ak
import pandas as pd
import os
import datetime
import time
import random
from colorama import init, Fore, Style

init(autoreset=True)

# 配置
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'input',
                          'akshare')


def fetch_with_retry(func, max_retries=5, initial_wait=3, *args, **kwargs):
    """
    带重试机制的数据拉取函数
    :param func: 要执行的 akshare 函数
    :param max_retries: 最大重试次数
    :param initial_wait: 初始等待秒数
    """
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            wait_time = initial_wait * (2 ** i) + random.uniform(0, 1)  # 指数退避 + 随机抖动
            print(f"{Fore.YELLOW}       ⚠️ 连接中断或失败: {e}")
            print(f"       ⏳ 第 {i + 1}/{max_retries} 次重试，等待 {wait_time:.1f} 秒...{Style.RESET_ALL}")
            time.sleep(wait_time)

    # 最后一次尝试
    print(f"{Fore.RED}       ❌ 重试多次仍失败，跳过此步骤。{Style.RESET_ALL}")
    raise Exception("Max retries exceeded")


def fetch_and_save_data(date_str=None):
    """
    拉取 Akshare 数据并保存为 CSV (增强稳健版)
    """
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y%m%d")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"{Fore.CYAN}🚀 开始拉取 Akshare 数据 (Date: {date_str})...{Style.RESET_ALL}")

    # 1. 获取全市场实时行情 (Spot Data)
    print(f"   📥 [1/5] 拉取全市场行情 (stock_zh_a_spot_em)...")
    df_spot = pd.DataFrame()
    try:
        # 使用重试机制调用
        df_spot = fetch_with_retry(ak.stock_zh_a_spot_em, max_retries=5)

        # 重命名
        df_spot.rename(columns={
            '代码': 'code', '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_chg',
            '成交额': 'amount', '流通市值': 'circ_mv', '换手率': 'turnover_rate',
            '量比': 'vol_ratio', '主力净流入': 'main_net_inflow'
        }, inplace=True)
        print(f"       ✅ 获取成功: {len(df_spot)} 条")
        time.sleep(2)  # 成功后也休息一下，防封
    except Exception as e:
        print(f"{Fore.RED}       ❌ 行情获取彻底失败，脚本无法继续: {e}{Style.RESET_ALL}")
        return  # 核心数据失败直接退出

    # 2. 获取涨停池数据
    print(f"   📥 [2/5] 拉取涨停池数据 (stock_zt_pool_em)...")
    df_zt = pd.DataFrame()
    try:
        df_zt = fetch_with_retry(ak.stock_zt_pool_em, date=date_str, max_retries=3)
        if df_zt.empty:
            print(f"{Fore.YELLOW}       ⚠️ 今日无涨停数据或非交易日{Style.RESET_ALL}")
            df_zt = pd.DataFrame(columns=['代码', '连板数', '涨停原因类别', '首次封板时间', '最后封板时间', '几天几板'])
        else:
            print(f"       ✅ 获取成功: {len(df_zt)} 条")
    except Exception as e:
        print(f"{Fore.RED}       ❌ 涨停池获取失败 (非交易日可忽略): {e}{Style.RESET_ALL}")
        # 构建一个空结构防止合并报错
        df_zt = pd.DataFrame(columns=['代码', '连板数', '涨停原因类别', '首次封板时间', '最后封板时间', '几天几板'])

    time.sleep(1)

    # 3. 数据合并
    print(f"   🔄 正在合并数据...")
    cols_zt = ['代码', '连板数', '涨停原因类别', '首次封板时间', '最后封板时间', '几天几板']
    cols_zt = [c for c in cols_zt if c in df_zt.columns]

    df_zt_clean = df_zt[cols_zt].copy()
    df_zt_clean.rename(columns={
        '代码': 'code', '连板数': 'limit_days', '涨停原因类别': 'reason',
        '几天几板': 'board_desc', '首次封板时间': 'first_zt_time', '最后封板时间': 'last_zt_time'
    }, inplace=True)

    df_merged = pd.merge(df_spot, df_zt_clean, on='code', how='left')
    df_merged['limit_days'] = df_merged['limit_days'].fillna(0).astype(int)
    df_merged.fillna('', inplace=True)

    # 4. 保存股票数据
    file_name = f"market_data_{date_str}.csv"
    file_path = os.path.join(OUTPUT_DIR, file_name)
    print(f"   💾 保存全市场数据到: {file_path}")
    df_merged.to_csv(file_path, index=False, encoding='utf-8-sig')

    # ==========================================
    # Phase 2: 板块与指数数据
    # ==========================================
    print(f"\n{Fore.CYAN}🚀 开始拉取板块与指数数据...{Style.RESET_ALL}")

    def save_category_data(df, category, prefix):
        if df.empty: return
        sub_dir = os.path.join(OUTPUT_DIR, category)
        if not os.path.exists(sub_dir): os.makedirs(sub_dir)
        f_name = f"{prefix}_chk_{date_str}.csv"
        f_path = os.path.join(sub_dir, f_name)
        print(f"   💾 保存 [{category}] 数据到: {f_path} ({len(df)}条)")
        df.to_csv(f_path, index=False, encoding='utf-8-sig')

    # 5. 拉取行业板块
    print(f"   📥 [3/5] 拉取行业板块...")
    try:
        # 增加 sleep 防止太快
        time.sleep(2)
        df_ind = fetch_with_retry(ak.stock_board_industry_name_em, max_retries=3)
        df_ind.rename(
            columns={'板块名称': 'name', '板块代码': 'code', '涨跌幅': 'pct_chg', '最新价': 'price', '成交额': 'amount',
                     '总市值': 'total_mv', '换手率': 'turnover_rate'}, inplace=True)
        save_category_data(df_ind, 'industries', 'industry')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 行业板块获取失败: {e}{Style.RESET_ALL}")

    # 6. 拉取概念板块
    print(f"   📥 [4/5] 拉取概念板块...")
    try:
        time.sleep(2)
        df_con = fetch_with_retry(ak.stock_board_concept_name_em, max_retries=3)
        df_con.rename(
            columns={'板块名称': 'name', '板块代码': 'code', '涨跌幅': 'pct_chg', '最新价': 'price', '成交额': 'amount',
                     '总市值': 'total_mv', '换手率': 'turnover_rate'}, inplace=True)
        save_category_data(df_con, 'concepts', 'concept')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 概念板块获取失败: {e}{Style.RESET_ALL}")

    # 7. 拉取主要指数
    print(f"   📥 [5/5] 拉取主要指数...")
    try:
        time.sleep(2)
        df_idx = fetch_with_retry(ak.stock_zh_index_spot_em, max_retries=3)
        df_idx.rename(columns={'指数代码': 'code', '指数名称': 'name', '最新价': 'price', '涨跌幅': 'pct_chg',
                               '成交额': 'amount'}, inplace=True)
        save_category_data(df_idx, 'indices', 'index')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 指数数据获取失败: {e}{Style.RESET_ALL}")

    print(f"{Fore.GREEN}✅ 所有任务完成!{Style.RESET_ALL}")


if __name__ == '__main__':
    fetch_and_save_data()