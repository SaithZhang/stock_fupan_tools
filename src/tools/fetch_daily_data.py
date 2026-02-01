import pywencai
import pandas as pd
import os
import sys
import time

# 解决 Windows 控制台中文乱码
sys.stdout.reconfigure(encoding='utf-8')

# ==========================================
# 路径配置
# ==========================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_FILE = os.path.join(PROJECT_ROOT, 'cookie.txt')


# 备用路径 (如果需要，取消注释)
# COOKIE_FILE = r"D:\work\pyproject\cookie.txt"

def get_cookie():
    """读取 Cookie"""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None


def split_and_merge_fetch():
    print(f"📂 正在读取 Cookie: {COOKIE_FILE}")
    cookie_str = get_cookie()

    if not cookie_str:
        print("❌ 未找到 Cookie，无法继续。")
        return

    # ==========================================
    # 1. 定义核心筛选和唯一键 (Row Filters & Keys)
    #    注意：每次请求都必须带上这些，保证拉取的股票名单是对齐的
    # ==========================================
    base_filter = "非ST, 非北交所"
    key_columns = ["股票代码", "股票简称"]

    # ==========================================
    # 2. 将复杂字段分组 (Column Groups)
    #    拆分原则：计算量大的字段单独放，基础字段放一组
    # ==========================================
    field_groups = [
        # Group 1: 基础行情 & 估值
        ["最新价", "涨跌幅", "成交额", "换手率", "量比", "流通市值"],

        # Group 2: 资金 & 竞价 (通常较慢，容易挂)
        ["主力资金流向", "竞价涨幅", "竞价金额"],

        # Group 3: 涨停分析 (打板相关)
        ["连续涨停天数", "几天几板", "涨停原因类别", "最终涨停时间", "首次涨停时间", "开板次数"],

        # Group 4: 趋势 & 行业 (文本类较长)
        ["10日涨幅", "20日涨幅", "所属同花顺行业", "所属概念"]
    ]

    final_df = None

    print(f"\n🚀 开始分批拉取，共 {len(field_groups)} 组请求...")
    print("-" * 60)

    for i, fields in enumerate(field_groups, 1):
        # 拼接查询语句： 筛选条件 + 唯一键 + 本组字段
        # 例如: "非ST, 非北交所, 股票代码, 股票简称, 最新价, 涨跌幅..."
        group_query = f"{base_filter}, {', '.join(key_columns)}, {', '.join(fields)}"

        print(f"📡 [第 {i} 组] 请求中... (包含: {fields[0]} 等 {len(fields)} 个字段)")

        try:
            # 发起请求
            df_chunk = pywencai.get(query=group_query, loop=True, cookie=cookie_str)

            if df_chunk is None or df_chunk.empty:
                print(f"⚠️ 警告: 第 {i} 组返回为空，跳过此组字段。")
                continue

            # 数据清洗：只保留我们需要的列（Key + 本次请求的 Fields）
            # 因为问财可能会返回多余的列，或者列名带有奇怪的后缀
            # 这里简单处理：不做强行过滤，依赖 merge 自动对齐

            if final_df is None:
                # 第一组直接作为基准
                final_df = df_chunk
                print(f"✅ [第 {i} 组] 成功，获取 {len(df_chunk)} 行数据。")
            else:
                # 后续组：与基准表进行合并 (Merge)
                # 注意：how='inner' 确保只保留两边都有的股票；on='股票代码'
                # 问财返回的 '股票代码' 列通常是唯一的，可以直接 merge

                # 检查一下 df_chunk 里有没有 '股票代码'
                if '股票代码' not in df_chunk.columns:
                    # 有时候可能是 'code'，做个容错
                    if 'code' in df_chunk.columns:
                        df_chunk.rename(columns={'code': '股票代码'}, inplace=True)
                    else:
                        print(f"❌ 错误: 第 {i} 组数据缺少 '股票代码' 列，无法合并。")
                        continue

                # 为了避免列名冲突（比如两边都有'股票简称'），我们可以只取 [key + new_fields]
                # 但更简单的办法是直接 merge，如果有重复列，pandas 会自动加 _x, _y 后缀，后续再清洗
                # 这里为了稳妥，我们手动筛选一下 df_chunk 的列
                cols_to_use = ['股票代码'] + [c for c in df_chunk.columns if
                                              c not in final_df.columns and c != '股票代码']

                # 执行合并
                final_df = pd.merge(final_df, df_chunk[cols_to_use], on='股票代码', how='left')
                print(f"✅ [第 {i} 组] 合并成功，当前总列数: {final_df.shape[1]}")

            # 💡 稍微 sleep 一下，防止请求过快被封
            time.sleep(1.5)

        except Exception as e:
            print(f"❌ [第 {i} 组] 发生异常: {e}")
            # 可以选择在这里 return 终止，或者 continue 继续拉下一组
            continue

    if final_df is not None:
        print("=" * 60)
        print(f"🎉 所有请求完成！最终数据: {final_df.shape[0]} 行, {final_df.shape[1]} 列")
        print("=" * 60)

        # 打印一下所有列名，方便你确认
        print("Columns:", final_df.columns.tolist())

        # 简单的展示前3行
        # print(final_df.head(3))

        # 如果需要保存
        # final_df.to_csv("wencai_merged_data.csv", index=False, encoding='utf-8-sig')
        # print("💾 已保存至 wencai_merged_data.csv")
    else:
        print("❌ 未获取到任何有效数据。")


if __name__ == "__main__":
    split_and_merge_fetch()