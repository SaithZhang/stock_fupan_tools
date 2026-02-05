# ==============================================================================
# 🔍 数据一致性校验 (check_diff.py)
# 职责：对比 V1 (旧版) 和 V2 (Tushare版) 的策略池结果，找出逻辑漏洞
# ==============================================================================

import pandas as pd
import os
import re
from colorama import init, Fore, Style

init(autoreset=True)

# 🛠️ 配置路径
V1_PATH = r"D:\work\pyproject\data\output\strategy_pool_20260204.csv"  # 替换为你的 V1 文件名
V2_PATH = r"D:\work\pyproject\data\output\strategy_pool_v2_20260204.csv"  # 替换为你的 V2 文件名


def extract_limit_days(tag_str):
    """从标签中提取连板数 (例如 '3板/趋势' -> 3)"""
    if not isinstance(tag_str, str): return 0
    match = re.search(r'(\d+)板', tag_str)
    return int(match.group(1)) if match else 0


def check_data():
    if not os.path.exists(V1_PATH) or not os.path.exists(V2_PATH):
        print(f"{Fore.RED}❌ 找不到文件，请检查文件名和路径")
        return

    print(f"{Fore.CYAN}📥 正在加载文件...")
    df1 = pd.read_csv(V1_PATH, dtype={'code': str})
    df2 = pd.read_csv(V2_PATH, dtype={'code': str})

    # 1. 数量对比
    print(f"\n{Fore.YELLOW}📊 [1. 数量对比]")
    print(f"   V1 (旧版) 数量: {len(df1)}")
    print(f"   V2 (新版) 数量: {len(df2)}")

    # 2. 标的重合度
    set1 = set(df1['code'])
    set2 = set(df2['code'])
    common = set1 & set2
    only_v1 = set1 - set2
    only_v2 = set2 - set1

    print(f"   ✅ 共同入选: {len(common)} 只")
    print(f"   ❌ V1有但在V2消失: {len(only_v1)} 只 (可能被误杀)")
    print(f"   🆕 V2新增: {len(only_v2)} 只")

    # 3. 核心字段逻辑校验 (仅对比共同存在的股票)
    df1_common = df1[df1['code'].isin(common)].set_index('code')
    df2_common = df2[df2['code'].isin(common)].set_index('code')

    # 对齐索引
    df2_common = df2_common.reindex(df1_common.index)

    print(f"\n{Fore.YELLOW}🧪 [2. 逻辑一致性体检 (基于共同标的)]")

    # Check A: 连板高度 (Tag 里的 'N板')
    df1_common['limit_days'] = df1_common['tag'].apply(extract_limit_days)
    df2_common['limit_days'] = df2_common['tag'].apply(extract_limit_days)

    diff_limit = df1_common[df1_common['limit_days'] != df2_common['limit_days']]
    if not diff_limit.empty:
        print(f"{Fore.RED}   ⚠️ 连板高度不一致: {len(diff_limit)} 只")
        print(f"      示例 (V1 vs V2):")
        for code in diff_limit.head(3).index:
            name = df1_common.loc[code, 'name']
            v1_b = df1_common.loc[code, 'limit_days']
            v2_b = df2_common.loc[code, 'limit_days']
            print(f"      - {name}: V1=[{v1_b}板] vs V2=[{v2_b}板]")
        print("      (如果 V2 全是 0 或 1，说明 limit_list 接口降级导致高标识别失效)")
    else:
        print(f"{Fore.GREEN}   ✅ 连板高度逻辑一致")

    # Check B: 成交额单位 (Amount)
    # 计算比例: V2 / V1
    # 避免除以0
    ratio = df2_common['amount'] / (df1_common['amount'] + 1)
    avg_ratio = ratio.mean()

    print(f"   💰 成交额单位检测 (Ratio = V2/V1): {avg_ratio:.4f}")
    if 0.9 < avg_ratio < 1.1:
        print(f"{Fore.GREEN}      ✅ 单位正常 (两者一致)")
    elif 9000 < avg_ratio < 11000:
        print(f"{Fore.RED}      ❌ 单位错误: V2 比 V1 大 10000 倍 (可能多乘了万)")
    elif 0.09 < avg_ratio < 0.11:
        print(f"{Fore.RED}      ❌ 单位错误: V2 比 V1 小 10 倍")
    else:
        print(f"{Fore.YELLOW}      ⚠️ 单位有差异，请人工核查")

    # Check C: 竞价金额
    v2_call_auc = df2_common['call_auction_ratio'].sum()
    if v2_call_auc == 0:
        print(f"{Fore.MAGENTA}   ⚠️ 确认: V2 版本竞价占比全为 0 (符合预期，Tushare暂缺分钟线)")
    else:
        print(f"   ℹ️ V2 有竞价数据")

    # 4. 消失的股票去哪了？(V1有 V2没有)
    if len(only_v1) > 0:
        print(f"\n{Fore.YELLOW}🕵️ [3. 消失标的分析 (Top 5)]")
        missing_df = df1[df1['code'].isin(list(only_v1)[:5])]
        for _, row in missing_df.iterrows():
            print(f"   - {row['name']} ({row['code']}): {row['tag']}")


if __name__ == "__main__":
    check_data()