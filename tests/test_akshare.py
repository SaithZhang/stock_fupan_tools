import akshare as ak
import pandas as pd
import time
from colorama import init, Fore, Style

# 初始化颜色
init(autoreset=True)


def test_eastmoney_industry():
    print(f"{Fore.CYAN}正在检查 Akshare 版本...{Style.RESET_ALL}")
    print(f"当前版本: {ak.__version__}")

    print(f"\n{Fore.CYAN}🚀 开始请求: ak.stock_board_industry_name_em() ...{Style.RESET_ALL}")

    start_time = time.time()
    try:
        # 核心测试代码
        df = ak.stock_board_industry_name_em()

        cost = time.time() - start_time

        if df is None or df.empty:
            print(f"{Fore.RED}❌ 请求成功，但返回数据为空！{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}✅ 成功获取数据！耗时: {cost:.2f}秒{Style.RESET_ALL}")
            print(f"数据形状: {df.shape} (行, 列)")
            print(f"列名: {df.columns.tolist()}")

            # 打印前5行，看有没有我们需要的'板块名称'和'涨跌幅'
            print("\n🔍 数据预览 (前5行):")
            print(df[['板块名称', '板块代码', '最新价', '涨跌幅', '领涨股票']].head().to_string())

            # 简单验证一下涨跌幅字段是否为数字
            try:
                test_val = df.iloc[0]['涨跌幅']
                print(f"\n数据类型检查: 第一行涨跌幅为 {test_val} (类型: {type(test_val)})")
            except:
                pass

    except Exception as e:
        print(f"{Fore.RED}❌ 发生异常: {e}{Style.RESET_ALL}")
        print("建议排查: 网络连接 / Akshare版本 / 接口是否变更")


if __name__ == "__main__":
    test_eastmoney_industry()