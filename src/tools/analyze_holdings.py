# ==============================================================================
# 📊 持仓做T战术分析工具 (src/tools/analyze_holdings.py)
# Version: 2.0 (Proxy Fix)
# ==============================================================================

import pandas as pd
import sys
import os
from io import StringIO
from colorama import init, Fore, Style

init(autoreset=True)

# ------------------------------------------------------------------------------
# 0. 环境路径修正 (确保能导入 src 模块)
# ------------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
# 向上推两级找到项目根目录 (假设结构是 project/src/tools/analyze_holdings.py)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ✅ 关键修正：导入你写好的 Client (包含代理配置)
try:
    from src.data.tushare_source.client import TushareClient
except ImportError as e:
    print(f"{Fore.RED}❌ 模块导入失败: {e}")
    print(f"请确保在项目根目录下运行，或检查 src/data/tushare_source/client.py 是否存在")
    sys.exit(1)

# ------------------------------------------------------------------------------
# 1. 你的持仓数据
# ------------------------------------------------------------------------------
HOLDING_DATA = """
证券代码\t证券名称\t股票余额\t实际数量\t可用余额\t冻结数量\t成本价\t市价\t盈亏\t盈亏比(%)\t当日盈亏\t当日盈亏比(%)\t市值\t仓位占比(%)\t当日买入\t当日卖出\t交易市场\t持股天数
002931\t锋龙股份\t1000\t1000\t400\t600\t108.250\t95.500\t-12750.230\t-11.78\t-10582.00\t-6.47\t95500.000\t18.32\t0\t0\t深Ａ\t4
002837\t英维克\t0\t500\t0\t0\t99.960\t99.500\t-230.000\t-0.46\t-225.00\t-0.45\t49750.000\t9.54\t0\t0\t深Ａ\t--
002149\t西部材料\t1000\t1000\t0\t1000\t48.920\t48.310\t-610.000\t-1.25\t-175.00\t-0.18\t48310.000\t9.27\t0\t0\t深Ａ\t2
603667\t五洲新春\t0\t500\t0\t0\t87.871\t87.450\t-210.440\t-0.48\t-205.00\t-0.47\t43725.000\t8.39\t0\t0\t沪Ａ\t--
300164\t通源石油\t0\t2000\t0\t0\t11.725\t11.540\t-370.000\t-1.58\t-360.00\t-1.54\t23080.000\t4.43\t0\t0\t深Ａ\t--
"""


class PositionAnalyzer:
    def __init__(self, data_str):
        self.df = self._parse_data(data_str)

        # ✅ 使用你的 Client 获取 pro 接口 (会自动注入代理配置)
        self.pro = TushareClient.get_pro()

        if self.pro:
            print(f"{Fore.GREEN}✅ Tushare 代理接口连接成功")
        else:
            print(f"{Fore.RED}❌ Tushare 连接失败，请检查 src/config/secrets.py 配置")

    def _parse_data(self, raw_data):
        """清洗并解析持仓文本"""
        lines = [line for line in raw_data.strip().split('\n') if line.strip()]
        df = pd.read_csv(StringIO('\n'.join(lines)), sep='\t')

        # 补全代码后缀
        def fix_code(row):
            code = str(row['证券代码']).zfill(6)
            market = str(row.get('交易市场', ''))
            if '沪' in market or code.startswith('6'): return f"{code}.SH"
            return f"{code}.SZ"

        df['ts_code'] = df.apply(fix_code, axis=1)
        return df

    def get_real_market_data(self, ts_code):
        """真正去抢 Tushare 数据"""
        if not self.pro:
            return {'ma5': 0, 'pressure': 0, 'support': 0}

        try:
            # 1. 获取日线 (判断趋势)
            df_daily = self.pro.daily(ts_code=ts_code, limit=20)
            if df_daily.empty:
                return {'ma5': 0, 'pressure': 0, 'support': 0}

            # 简单计算 MA5
            ma5 = df_daily['close'][:5].mean()
            latest_close = df_daily.iloc[0]['close']

            # 2. 获取分钟线 (计算支撑压力) - 取最近24根60分钟K线
            df_min = self.pro.stk_mins(ts_code=ts_code, freq='60min', limit=24)

            pressure = 0
            support = 0
            if not df_min.empty:
                pressure = df_min['high'].max()
                support = df_min['close'].mean()

            return {
                'ma5': ma5,
                'pressure': pressure,
                'support': support,
                'latest_close': latest_close
            }
        except Exception as e:
            print(f"   ⚠️ 数据获取失败 {ts_code}: {e}")
            return {'ma5': 0, 'pressure': 0, 'support': 0}

    def analyze(self):
        print(f"\n{Fore.CYAN}🔎 持仓深度诊断报告 (正在连接代理接口获取实时数据...)")
        print("=" * 100)
        print(
            f"{'代码':<10} {'名称':<8} {'持仓价':<8} {'实时价':<8} {'MA5线':<8} {'支撑/压力':<16} {'状态':<8} {'建议策略'}")
        print("-" * 100)

        for _, row in self.df.iterrows():
            code = row['ts_code']
            name = row['证券名称']
            holding_price = row.get('市价', 0)  # 持仓软件显示的价格

            # 🔥 调用 API
            market_data = self.get_real_market_data(code)

            ma5 = market_data.get('ma5', 0)
            pressure = market_data.get('pressure', 0)
            support = market_data.get('support', 0)
            real_price = market_data.get('latest_close', 0)

            # 决策价格：如果有实时价格用实时的，否则用持仓的
            current_p = real_price if real_price > 0 else holding_price

            # --- 策略逻辑 ---
            advice = []
            status_str = "未知"
            status_color = Fore.WHITE

            if ma5 > 0:
                # 趋势判断
                if current_p < ma5:
                    status_str = "破位"
                    status_color = Fore.MAGENTA
                    advice.append("🚫 线下不买")
                else:
                    status_str = "多头"
                    status_color = Fore.RED
                    advice.append("🟢 线上持股")

                # 做T判断
                if pressure > 0:
                    if current_p >= pressure * 0.99:
                        advice.append(f"💰 触顶卖({pressure:.2f})")
                    elif current_p <= support * 1.01:
                        advice.append(f"🛒 回踩买({support:.2f})")
            else:
                advice.append("⚠️ 无数据")

            supp_press_str = f"{support:.1f}/{pressure:.1f}"

            # 格式化输出
            print(
                f"{status_color}{code:<10} {name:<8} {holding_price:<8.2f} {current_p:<8.2f} "
                f"{ma5:<8.2f} {supp_press_str:<16} {status_str:<8} {' | '.join(advice)}{Style.RESET_ALL}"
            )

        print("=" * 100)


if __name__ == "__main__":
    analyzer = PositionAnalyzer(HOLDING_DATA)
    analyzer.analyze()