# ==============================================================================
# 📺 竞价监控 V2 (src/monitors/call_auction_screener_v2.py)
# Version: 4.0 (Tushare V3 RT_K)
# 核心功能：全市场竞价扫描 + 弱转强识别 + 爆量异动筛选
# ==============================================================================

import os
import sys
import time
import pandas as pd
import numpy as np
from colorama import init, Fore, Style

# --- 环境设置 ---
init(autoreset=True)
if sys.platform == 'win32':
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.extend([current_dir, project_root, os.path.join(project_root, 'src')])

try:
    from src.config.settings import Config
    from src.utils.text_tools import TextUtils
    from src.data.tushare_manager import TushareManager
    from src.strategies.auction import AuctionStrategy
except ImportError as e:
    print(f"{Fore.RED}❌ 模块加载失败: {e}")
    sys.exit(1)


class AuctionAppV2:
    def __init__(self):
        self.ts_manager = TushareManager()
        self.strategy_pool = {}  # 昨晚复盘的策略池 {code: {tag, name, ...}}
        self.holdings = set()  # 持仓代码集合

    def load_resources(self):
        """加载昨晚复盘结果 + 持仓"""
        print(f"{Fore.CYAN}📥 [V2] 正在加载策略池与持仓数据...")

        # 1. 加载持仓 (用于高亮)
        if os.path.exists(Config.HOLDINGS_PATH):
            raw = TextUtils.load_text_list(Config.HOLDINGS_PATH)
            for c in raw:
                # 兼容 600000.SH 和 600000 两种格式
                pure_code = c.split('.')[0]
                self.holdings.add(pure_code)

        # 2. 加载昨日策略池 (用于对比弱转强)
        # 必须包含字段：code, name, tag, today_pct(昨日涨幅), amount(昨日成交额), vol(昨日成交量)
        pool_path = os.path.join(Config.OUTPUT_DIR, 'strategy_pool.csv')
        if os.path.exists(pool_path):
            try:
                df = pd.read_csv(pool_path, dtype={'code': str})
                for _, row in df.iterrows():
                    code = str(row['code']).zfill(6)
                    self.strategy_pool[code] = {
                        'name': str(row.get('name', '未知')),
                        'tag': str(row.get('tag', '')),
                        'yest_pct': float(row.get('today_pct', 0)),
                        'yest_vol': float(row.get('vol', 0)),  # 昨日全天量(手)
                        'yest_amt': float(row.get('amount', 0)),  # 昨日全天额
                        'yest_close': float(row.get('price', 0))  # 昨日收盘价
                    }
            except Exception as e:
                print(f"{Fore.RED}❌ 策略池读取失败: {e}")
        else:
            print(f"{Fore.YELLOW}⚠️ 未找到 strategy_pool.csv，弱转强判定将失效")

        print(f"✅ 资源就绪: 持仓 {len(self.holdings)} | 策略池 {len(self.strategy_pool)}")

    def _format_amt(self, amt):
        """金额格式化"""
        if pd.isna(amt) or amt == 0: return "-"
        if amt >= 1_0000_0000:
            return f"{amt / 1_0000_0000:.1f}亿"
        else:
            return f"{int(amt / 10000)}万"

    def fetch_market_auction(self):
        """
        使用 Tushare V3 rt_k 接口获取全市场数据
        """
        print(f"\n{Fore.YELLOW}🚀 正在拉取全市场竞价数据 (Tushare rt_k)...")
        start_t = time.time()

        try:
            # 批量获取主板、创业板、科创板、北交所
            # 注意：单次提取建议分批，但 rt_k 支持通配符一次性获取（视积分权限而定）
            # 如果积分不够，可能需要缩小范围或分批调用
            codes = '6*.SH,0*.SZ,3*.SZ,688*.SH,8*.BJ,4*.BJ'
            df = self.ts_manager.pro.rt_k(ts_code=codes)

            if df.empty:
                print(f"{Fore.RED}❌ 接口返回为空 (可能未到竞价时间或权限不足)")
                return pd.DataFrame()

            # 耗时统计
            print(f"{Fore.GREEN}✅ 拉取成功: {len(df)} 条数据 | 耗时: {time.time() - start_t:.2f}s")
            return df

        except Exception as e:
            print(f"{Fore.RED}❌ Tushare 接口异常: {e}")
            return pd.DataFrame()

    def run(self):
        self.load_resources()

        # 1. 获取实时竞价数据
        df_rt = self.fetch_market_auction()
        if df_rt.empty: return

        # 2. 数据清洗与计算
        results = []

        # 预处理：rt_k 返回的 vol 是股，amount 是元
        # 9:25-9:30 期间，open 即为竞价开盘价，vol 即为竞价量

        for _, row in df_rt.iterrows():
            ts_code = row['ts_code']
            code = ts_code.split('.')[0]

            # --- 基础数据 ---
            # 现价 (在竞价阶段 open 就是 current price)
            current_price = float(row['open'])
            pre_close = float(row['pre_close'])

            # 停牌过滤
            if current_price == 0: continue

            # 竞价涨幅
            auc_pct = (current_price - pre_close) / pre_close * 100

            # 竞价成交额 (元)
            auc_amt = float(row['amount'])

            # 竞价成交量 (股) -> 转为手
            auc_vol_shou = float(row['vol']) / 100

            # --- 结合策略池匹配 ---
            # 默认为空策略
            strategy_info = self.strategy_pool.get(code, {})

            name = row['name']
            if not name and 'name' in strategy_info:
                name = strategy_info['name']

            tag = strategy_info.get('tag', '')
            yest_pct = strategy_info.get('yest_pct', 0)
            yest_vol = strategy_info.get('yest_vol', 0)

            # --- 核心指标计算 ---

            # 1. 爆量比 (Auction Ratio) = 竞价量 / 昨日全天量
            # 这是一个非常关键的指标，通常 > 0.05 (5%) 表示主力有备而来
            auc_ratio = 0.0
            if yest_vol > 0:
                auc_ratio = auc_vol_shou / yest_vol

            # 2. 弱转强判定
            # 逻辑：昨日烂板/阴线 (yest_pct < 9.5) + 今日高开 (auc_pct > 2) + 爆量 (auc_ratio > 0.05)
            is_weak_turn_strong = False
            status_desc = ""

            if code in self.strategy_pool:
                # 策略池中的标的才通过这里详细判断状态
                if yest_pct < 5 and auc_pct > 2 and auc_ratio > 0.03:
                    is_weak_turn_strong = True
                    status_desc = f"{Fore.RED}★弱转强{Style.RESET_ALL}"
                elif auc_pct > 5:
                    status_desc = f"{Fore.RED}抢筹{Style.RESET_ALL}"
                elif auc_pct < -3:
                    status_desc = f"{Fore.GREEN}核按钮{Style.RESET_ALL}"
            else:
                # 非策略池标的，如果是首板/突发利好，也可能有大爆量
                if auc_pct > 5 and auc_amt > 2000_0000:  # 竞价金额大于2000万
                    status_desc = f"{Fore.MAGENTA}突发异动{Style.RESET_ALL}"

            # --- 筛选逻辑 (决定是否显示) ---
            # 显示条件：
            # 1. 在我的持仓中
            # 2. 在我的策略池中
            # 3. 市场突发大金额异动 (竞价 > 3000万) 且 涨幅 > 2%

            is_holding = code in self.holdings
            in_pool = code in self.strategy_pool
            is_market_hot = (auc_amt > 3000_0000 and auc_pct > 1.0)

            if not (is_holding or in_pool or is_market_hot):
                continue

            # --- 格式化输出 ---

            # 名称颜色
            name_display = name
            if is_holding:
                name_display = f"{Fore.MAGENTA}{name}{Style.RESET_ALL}"

            # 涨幅颜色
            pct_color = Fore.RED if auc_pct > 0 else (Fore.GREEN if auc_pct < 0 else Fore.WHITE)

            # 爆量颜色
            ratio_str = f"{auc_ratio * 100:.1f}%"
            if auc_ratio > 0.10:  # 竞价超10%极其夸张
                ratio_str = f"{Fore.RED}{ratio_str}{Style.RESET_ALL}"
            elif auc_ratio > 0.05:
                ratio_str = f"{Fore.YELLOW}{ratio_str}{Style.RESET_ALL}"

            # 排序权重
            # 持仓最前 > 弱转强 > 竞价金额大
            sort_score = 0
            if is_holding: sort_score += 10000
            if is_weak_turn_strong: sort_score += 5000
            if in_pool: sort_score += 1000
            sort_score += auc_pct  # 涨幅高的排前面

            results.append({
                'code': code,
                'name': name_display,
                'auc_pct': auc_pct,
                'pct_color': pct_color,
                'price': current_price,
                'auc_amt': auc_amt,
                'auc_amt_str': self._format_amt(auc_amt),
                'auc_ratio_str': ratio_str,
                'auc_ratio': auc_ratio,
                'yest_pct': yest_pct,
                'tag': tag,
                'status': status_desc,
                'sort_score': sort_score
            })

        # --- 排序与打印 ---
        results.sort(key=lambda x: x['sort_score'], reverse=True)

        # 只显示前 50 条，避免刷屏
        display_list = results[:50]

        print("-" * 110)
        print(f"{'代码':<8}{'名称':<14}{'竞价%':<10}{'现价':<8}{'竞价金额':<10}{'爆量比':<10}{'昨幅%':<8}{'标签/状态'}")
        print("-" * 110)

        for r in display_list:
            print(
                f"{r['code']:<8}"
                f"{r['name']:<24}"  # 包含颜色代码，长度需留足
                f"{r['pct_color']}{r['auc_pct']:>6.2f}%{Style.RESET_ALL}   "
                f"{r['price']:<8.2f}"
                f"{Fore.YELLOW}{r['auc_amt_str']:<10}{Style.RESET_ALL}"
                f"{r['auc_ratio_str']:<18}"  # 包含颜色代码
                f"{r['yest_pct']:>6.2f}%  "
                f"{r['status']} {Fore.CYAN}{r['tag']}{Style.RESET_ALL}"
            )
        print("-" * 110)


if __name__ == "__main__":
    try:
        app = AuctionAppV2()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"程序异常退出: {e}")
        import traceback

        traceback.print_exc()