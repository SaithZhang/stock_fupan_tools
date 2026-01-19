
import akshare as ak
import pandas as pd
import os
import datetime
import time
from colorama import init, Fore, Style

init(autoreset=True)

# 配置
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'input', 'akshare')

def fetch_and_save_data(date_str=None):
    """
    拉取 Akshare 数据并保存为 CSV
    :param date_str: YYYYMMDD (默认为即时/今日)
    """
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y%m%d")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"{Fore.CYAN}🚀 开始拉取 Akshare 数据 (Date: {date_str})...{Style.RESET_ALL}")
    
    # 1. 获取全市场实时行情 (Spot Data)
    # 注意: 这个接口只能获取"当前"的快照。如果是盘后运行，就是收盘数据。
    # 无法指定日期获取历史的 spot 数据。
    print(f"   📥 [1/2] 拉取全市场行情 (stock_zh_a_spot_em)...")
    try:
        df_spot = ak.stock_zh_a_spot_em()
        # 重命名以对齐 (方便后续使用)
        df_spot.rename(columns={
            '代码': 'code',
            '名称': 'name',
            '最新价': 'price',
            '涨跌幅': 'pct_chg',
            '成交额': 'amount',
            '流通市值': 'circ_mv',
            '换手率': 'turnover_rate',
            '量比': 'vol_ratio',
            '主力净流入': 'main_net_inflow'
        }, inplace=True)
        print(f"       ✅ 获取成功: {len(df_spot)} 条")
    except Exception as e:
        print(f"{Fore.RED}       ❌ 行情获取失败: {e}{Style.RESET_ALL}")
        return

    # 2. 获取涨停池数据 (Limit Up Pool)
    # 这个接口支持 historical date
    print(f"   📥 [2/2] 拉取涨停池数据 (stock_zt_pool_em) 日期={date_str}...")
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if df_zt.empty:
             print(f"{Fore.YELLOW}       ⚠️ 今日无涨停数据或非交易日{Style.RESET_ALL}")
             df_zt = pd.DataFrame(columns=['代码', '连板数', '涨停原因类别', '首次封板时间', '最后封板时间', '几天几板'])
        else:
             print(f"       ✅ 获取成功: {len(df_zt)} 条")
    except Exception as e:
        print(f"{Fore.RED}       ❌ 涨停池获取失败: {e} (可能无需恐慌，若是非交易日){Style.RESET_ALL}")
        df_zt = pd.DataFrame()

    # 3. 数据合并
    print(f"   🔄 正在合并数据...")
    
    # 准备 ZT 数据用于 merge
    # 只要关键几列
    cols_zt = ['代码', '连板数', '涨停原因类别', '首次封板时间', '最后封板时间', '几天几板']
    # 过滤掉不存在的列以防万一
    cols_zt = [c for c in cols_zt if c in df_zt.columns]
    
    df_zt_clean = df_zt[cols_zt].copy()
    df_zt_clean.rename(columns={
        '代码': 'code',
        '连板数': 'limit_days',
        '涨停原因类别': 'reason',
        '几天几板': 'board_desc',
        '首次封板时间': 'first_zt_time',
        '最后封板时间': 'last_zt_time'
    }, inplace=True)
    
    # Merge: Left join spot with zt
    df_merged = pd.merge(df_spot, df_zt_clean, on='code', how='left')
    
    # 填充 NaN
    df_merged['limit_days'] = df_merged['limit_days'].fillna(0).astype(int)
    from numpy import nan
    df_merged.fillna('', inplace=True) # 其他填空字符串

    # 4. 保存股票数据
    file_name = f"market_data_{date_str}.csv"
    file_path = os.path.join(OUTPUT_DIR, file_name)
    
    print(f"   💾 保存全市场数据到: {file_path}")
    df_merged.to_csv(file_path, index=False, encoding='utf-8-sig')

    # ==========================================
    # Phase 2: 板块与指数数据 (Industries, Concepts, Indices)
    # ==========================================
    print(f"\n{Fore.CYAN}🚀 开始拉取板块与指数数据...{Style.RESET_ALL}")
    
    # 定义辅助保存函数
    def save_category_data(df, category, prefix):
        if df.empty: return
        sub_dir = os.path.join(OUTPUT_DIR, category)
        if not os.path.exists(sub_dir): os.makedirs(sub_dir)
        
        f_name = f"{prefix}_chk_{date_str}.csv"
        f_path = os.path.join(sub_dir, f_name)
        print(f"   💾 保存 [{category}] 数据到: {f_path} ({len(df)}条)")
        df.to_csv(f_path, index=False, encoding='utf-8-sig')

    # 5. 拉取行业板块 (Industries)
    print(f"   📥 [3/5] 拉取行业板块 (stock_board_industry_name_em)...")
    try:
        df_ind = ak.stock_board_industry_name_em()
        # 简单重命名
        df_ind.rename(columns={'板块名称': 'name', '板块代码': 'code', '涨跌幅': 'pct_chg', '最新价': 'price', '成交额': 'amount', '总市值': 'total_mv', '换手率': 'turnover_rate'}, inplace=True)
        save_category_data(df_ind, 'industries', 'industry')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 行业板块获取失败: {e}{Style.RESET_ALL}")

    # 6. 拉取概念板块 (Concepts)
    print(f"   📥 [4/5] 拉取概念板块 (stock_board_concept_name_em)...")
    try:
        df_con = ak.stock_board_concept_name_em()
        df_con.rename(columns={'板块名称': 'name', '板块代码': 'code', '涨跌幅': 'pct_chg', '最新价': 'price', '成交额': 'amount', '总市值': 'total_mv', '换手率': 'turnover_rate'}, inplace=True)
        save_category_data(df_con, 'concepts', 'concept')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 概念板块获取失败: {e}{Style.RESET_ALL}")

    # 7. 拉取主要指数 (Indices)
    print(f"   📥 [5/5] 拉取主要指数 (stock_zh_index_spot_em)...")
    try:
        # 不传参获取全部指数 (包含主要指数)
        df_idx = ak.stock_zh_index_spot_em()
        df_idx.rename(columns={'指数代码': 'code', '指数名称': 'name', '最新价': 'price', '涨跌幅': 'pct_chg', '成交额': 'amount'}, inplace=True)
        save_category_data(df_idx, 'indices', 'index')
    except Exception as e:
        print(f"{Fore.RED}       ❌ 指数数据获取失败: {e}{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}✅ 所有任务完成!{Style.RESET_ALL}")

if __name__ == '__main__':
    fetch_and_save_data()
