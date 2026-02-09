# ==============================================================================
# 🌍 市场大盘数据展示器 (src/data/market_data.py)
# Version: 4.0 (State Container Only)
# ==============================================================================
from colorama import Fore


class MarketDataManager:
    def __init__(self):
        # 核心指数数据容器
        self.indices = {
            'sh': {'name': '上证指数', 'amount': 0, 'pct': 0.0},
            'sz': {'name': '深证成指', 'amount': 0, 'pct': 0.0},
            'gz': {'name': '国证2000', 'amount': 0, 'pct': 0.0},
        }

        # 统计数据
        self.stats = {
            'zt_count': 0,  # 涨停
            'dt_count': 0,  # 跌停
            'lb_height': 0  # 连板高度
        }

        # 阶段信息
        self.phase_info = {'phase': 'N/A', 'action_guide': '观察'}

    def update_indices(self, index_data: dict):
        """
        注入 fetcher 获取的指数数据
        :param index_data: {'sh': {'pct': 1.2, 'amount': 10000...}, ...}
        """
        if not index_data: return
        for k, v in index_data.items():
            if k in self.indices:
                self.indices[k].update(v)

    def update_stats(self, stats_dict: dict):
        """
        注入 fetcher 获取的涨跌停统计 或 阶段信息
        :param stats_dict: {'limit_up_count': 50, ...} OR {'phase': '主升'}
        """
        if not stats_dict: return

        # 1. 更新涨跌停统计
        if 'limit_up_count' in stats_dict: self.stats['zt_count'] = stats_dict['limit_up_count']
        if 'limit_down_count' in stats_dict: self.stats['dt_count'] = stats_dict['limit_down_count']
        if 'highest_plate' in stats_dict: self.stats['lb_height'] = stats_dict['highest_plate']

        # 2. 更新阶段信息
        if 'phase' in stats_dict:
            self.phase_info = stats_dict

    def get_formatted_summary(self):
        """生成最终 Summary 字符串"""
        # 总金额 = 上证 + 深证
        total = self.indices['sh']['amount'] + self.indices['sz']['amount']
        total_str = f"{total / 100000000:.0f}亿"

        sh_pct = self.indices['sh']['pct']

        # 优先用国证代表情绪，没有则用深证
        gz_data = self.indices['gz']
        use_gz = gz_data['amount'] > 0
        sub_name = "国证" if use_gz else "深证"
        sub_pct = gz_data['pct'] if use_gz else self.indices['sz']['pct']

        # 颜色
        sh_c = Fore.RED if sh_pct > 0 else Fore.GREEN
        sub_c = Fore.RED if sub_pct > 0 else Fore.GREEN

        # 阶段图标
        phase = self.phase_info.get('phase', '震荡')
        icon = "🌊"
        if "主升" in phase or "普涨" in phase:
            icon = "🚀"
        elif "退潮" in phase or "冰点" in phase:
            icon = "❄️"
        elif "分歧" in phase:
            icon = "⚔️"

        # 组装文案
        return (
            f"📊 大盘: {total_str} | "
            f"上证{sh_c}{sh_pct:+.2f}%{Fore.YELLOW} {sub_name}{sub_c}{sub_pct:+.2f}%{Fore.YELLOW} | "
            f"涨停{Fore.RED}{self.stats['zt_count']}{Fore.YELLOW}家 跌停{Fore.GREEN}{self.stats['dt_count']}{Fore.YELLOW}家 | "
            f"{icon} {phase}"
        )