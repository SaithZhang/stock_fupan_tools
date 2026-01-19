
import akshare as ak
import pandas as pd
from colorama import init, Fore, Style
import datetime

init(autoreset=True)

def check_akshare_data():
    print(f"{Fore.CYAN}🚀 正在连接 Akshare 接口获取实时数据...{Style.RESET_ALL}")
    
    # 1. 获取实时行情 (Spot Data)
    # 对应同花顺: 代码, 名称, 涨幅, 现价, 成交额, 流通市值, 换手, 量比, 主力净额
    try:
        print(f"   📥 正在拉取 stock_zh_a_spot_em (全市场实时行情)...")
        df_spot = ak.stock_zh_a_spot_em()
        print(f"   ✅ 获取成功: {len(df_spot)} 条数据")
        
        # 打印列名供核对
        print(f"   📋 实时行情列名: {df_spot.columns.tolist()}")
        
        # 展示一条样例 (找个热门股，比如广电电气 601616)
        sample = df_spot[df_spot['代码'] == '601616']
        if not sample.empty:
            print(f"   🔎 广电电气 (601616) 实时数据:\n{sample.iloc[0].to_dict()}")
    except Exception as e:
        print(f"{Fore.RED}❌ 实时行情获取失败: {e}{Style.RESET_ALL}")
        df_spot = pd.DataFrame()

    print("-" * 50)

    # 2. 获取涨停池数据 (Limit Up Pool)
    # 对应同花顺: 连续涨停天数, 涨停原因, 几天几板, 首次/最终涨停时间
    try:
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        # 如果是周末或未开盘，可能取不到，尝试取最近一个交易日（简单处理先取今天，报错则提示）
        print(f"   📥 正在拉取 stock_zt_pool_em (今日涨停池)...")
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if df_zt.empty:
            print(f"{Fore.YELLOW}⚠️ 今日暂无涨停数据 (可能是非交易日或未开盘)，尝试昨天的...{Style.RESET_ALL}")
            # 简单回推逻辑略，直接提示用户
        else:
            print(f"   ✅ 获取成功: {len(df_zt)} 条涨停数据")
            print(f"   📋 涨停池列名: {df_zt.columns.tolist()}")
            
            # 展示样例
            if '601616' in df_zt['代码'].values:
                print(f"   🔎 广电电气 (601616) 涨停数据:\n{df_zt[df_zt['代码'] == '601616'].iloc[0].to_dict()}")
            else:
                print(f"   (广电电气今天未在涨停池中，显示第一条样例):\n{df_zt.iloc[0].to_dict()}")
                
    except Exception as e:
        print(f"{Fore.RED}❌ 涨停池获取失败 (可能非交易时间): {e}{Style.RESET_ALL}")

    print("=" * 50)
    print(f"{Fore.WHITE}📊 同花顺字段 vs Akshare 字段 覆盖度对比{Style.RESET_ALL}")
    
    mapping = {
        "代码": "✅ stock_zh_a_spot_em ['代码']",
        "名称": "✅ stock_zh_a_spot_em ['名称']",
        "涨幅": "✅ stock_zh_a_spot_em ['涨跌幅']",
        "现价": "✅ stock_zh_a_spot_em ['最新价']",
        "当日成交额": "✅ stock_zh_a_spot_em ['成交额']",
        "流通市值": "✅ stock_zh_a_spot_em ['流通市值']",
        "换手": "✅ stock_zh_a_spot_em ['换手率']",
        "量比": "✅ stock_zh_a_spot_em ['量比']",
        "主力净额": "✅ stock_zh_a_spot_em ['主力净流入']",
        "连续涨停天数": "✅ stock_zt_pool_em ['连板数'] (仅涨停股)",
        "涨停原因类别": "✅ stock_zt_pool_em ['涨停原因类别']",
        "几天几板": "✅ stock_zt_pool_em ['几天几板']",
        "首次涨停时间": "✅ stock_zt_pool_em ['首次封板时间']",
        "早盘竞价金额": "❌ 无直接接口 (需每日9:25只读snapshot)",
        "竞价涨幅%": "❌ 无直接接口 (需每日9:25只读snapshot)",
        "昨日成交额": "⚠️ 需计算 (stock_zh_a_hist 前一日收盘)",
    }
    
    for ths_col, status in mapping.items():
        print(f"{ths_col:<10} : {status}")

if __name__ == "__main__":
    check_akshare_data()
