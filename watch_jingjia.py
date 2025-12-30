import akshare as ak
import pandas as pd
from colorama import init, Fore, Style
from tabulate import tabulate
import time

init(autoreset=True)

# ================= 核心监控池 (F佬+Bo佬严选) =================
# 格式: '代码': {'name': '名称', 'tag': '逻辑标签', 'ref_price': 昨日收盘价(选填), 'limit_margin': 异动余量(选填)}
# 注意：代码需要带前缀 (sh/sz) 以便akshare识别，或者我们脚本里自动处理
WATCH_LIST = {
    '002361': {'name': '神剑股份', 'tag': '总龙/破局', 'last_close': 14.49, 'limit_space': -3.0},  # 已破
    '000547': {'name': '航天发展', 'tag': '控异动/0.2%', 'last_close': 30.98, 'limit_space': 0.2},  # 极危
    '002788': {'name': '鹭燕医药', 'tag': '控异动/趋势', 'last_close': 0.0, 'limit_space': 10},  # 需填昨收
    '600118': {'name': '中国卫星', 'tag': '弱转强/中军', 'last_close': 28.88, 'is_rotten': True},
    '600151': {'name': '航天机电', 'tag': '弱转强/卡位', 'last_close': 8.29, 'is_rotten': True},
    '603123': {'name': '翠微股份', 'tag': '弱转强/金融', 'last_close': 16.03, 'is_rotten': True},
    '002682': {'name': '龙洲股份', 'tag': '出监管/预期', 'last_close': 0.0, 'limit_space': 10},
    '600693': {'name': '东百集团', 'tag': '消费/核按钮', 'last_close': 0.0, 'limit_space': 10},
    '000592': {'name': '平潭发展', 'tag': '尾盘抢筹', 'last_close': 0.0, 'limit_space': 10},
    '104124': {'name': '雷科防务', 'tag': '航天/先锋', 'last_close': 10.37, 'limit_space': 10},  # 这里的代码需修正为6位
    '002413': {'name': '雷科防务', 'tag': '航天/先锋', 'last_close': 5.60, 'limit_space': 10},  # 修正代码
}


def get_realtime_quotes():
    """获取实时行情"""
    print(f"{Fore.CYAN}⏳ 正在拉取 9:25 竞价数据...{Style.RESET_ALL}")

    try:
        # 获取全市场实时行情 (速度可能稍慢，建议优化为只查特定代码，但akshare接口通常是全量的)
        # 也可以使用 stock_zh_a_spot_em()
        df = ak.stock_zh_a_spot_em()

        # 过滤我们的监控列表
        result = []

        for code, info in WATCH_LIST.items():
            # 找到对应代码的行
            row = df[df['代码'] == code]

            if row.empty:
                # 尝试修复代码前缀问题? akshare返回的是纯数字代码
                continue

            price_now = row.iloc[0]['最新价']
            open_price = row.iloc[0]['今开']
            pre_close = row.iloc[0]['昨收']
            amount = row.iloc[0]['成交额']  # 注意：竞价期间成交额可能显示为0或虚拟撮合额

            # 竞价未开出时，今开可能为0
            if open_price == 0: open_price = price_now

            # 计算开盘涨幅
            pct = (open_price - pre_close) / pre_close * 100

            # 逻辑判断
            status = ""

            # 1. 弱转强判定
            if info.get('is_rotten') and pct > 0:
                status += f"{Fore.RED}🔥弱转强成功 {Style.RESET_ALL}"
            elif info.get('is_rotten') and pct < -2:
                status += f"{Fore.GREEN}不及预期 {Style.RESET_ALL}"

            # 2. 异动监管判定 (针对航发)
            if 'limit_space' in info:
                space = info['limit_space']
                if abs(space) < 5:  # 只关注临界点
                    if pct > space:
                        status += f"{Fore.MAGENTA}⚠️触发监管({pct:.1f}% > {space}%){Style.RESET_ALL}"
                    else:
                        status += f"{Fore.CYAN}安全控盘 {Style.RESET_ALL}"

            # 3. 核按钮判定
            if pct < -5:
                status += f"{Fore.GREEN}☠️核按钮 {Style.RESET_ALL}"
            elif pct > -2 and '核按钮' in info['tag']:
                status += f"{Fore.RED}✨有修复 {Style.RESET_ALL}"

            # 资金显示 (万)
            amount_str = f"{int(amount / 10000)}万"

            # 颜色处理
            name_display = info['name']
            pct_display = f"{pct:.2f}%"
            if pct > 0:
                pct_display = f"{Fore.RED}{pct_display}{Style.RESET_ALL}"
            elif pct < 0:
                pct_display = f"{Fore.GREEN}{pct_display}{Style.RESET_ALL}"

            result.append([
                code,
                name_display,
                info['tag'],
                pct_display,
                amount_str,
                status
            ])

        return result

    except Exception as e:
        print(f"Error: {e}")
        return []


def main():
    table = get_realtime_quotes()
    if table:
        headers = ["代码", "名称", "核心逻辑", "开盘涨幅", "竞价金额", "F佬/Bo佬判定"]
        print("\n" + "=" * 80)
        print(tabulate(table, headers=headers, tablefmt="simple"))
        print("=" * 80)
        print(
            "📌 提示: \n1. 弱转强：昨日烂板 + 今日高开\n2. 航发若涨幅 > 0.2% 则触发200%异动，需谨慎\n3. 金额过小说明资金没来，需结合9:30后观察")


if __name__ == "__main__":
    main()