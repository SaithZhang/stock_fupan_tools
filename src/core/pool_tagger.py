# ==============================================================================
# 🧠 策略逻辑层 (src/core/pool_tagger.py)
# 作用: 接收纯净数据，判断是否入选，打上各种标签 (F佬/龙虎榜/焚诀/风险等)
# ==============================================================================
import re
import pandas as pd
from src.config.pool_config import CORE_KEYWORDS

# 尝试导入策略模块 (如果缺少则降级处理)
try:
    from src.strategies.ddd_mode import get_ddd_pool_category
except ImportError:
    def get_ddd_pool_category(*args): return None

try:
    from src.strategies.f_lao_model import check_fen_jue
except ImportError:
    def check_fen_jue(*args): return []

try:
    from src.tools.chip_analyzer import get_chip_metrics, generate_chip_tag
except ImportError:
    def get_chip_metrics(*args): return None
    def generate_chip_tag(*args): return ""

class PoolTagger:
    @staticmethod
    def process(item, context):
        """
        核心处理函数
        :param item: 单只股票的基础数据 (Dict)
        :param context: 上下文数据 (包含 holdings, lists, history, risk, lhb 等)
        :return: (is_selected, enriched_item)
        """
        code = item['code']
        name = item['name']
        
        # 1. 基础过滤
        if 'ST' in name.upper():
            return False, item

        is_selected = False
        tags = []
        
        # --- A. 涨停逻辑 ---
        if item['is_zt']:
            is_selected = True
            days = item['limit_days']
            tags.append(f"{days}板" if days > 1 else "首板")

        # --- B. 身份逻辑 (持仓/F佬) ---
        cleaned_manual = ""
        if code in context['holdings']:
            is_selected = True
            tags.append(f"持仓/{name}")
        elif code in context['flao']:
            is_selected = True
            # 清洗 F佬 标签
            note = context['flao'][code]
            note = PoolTagger._clean_manual_tag(note, item['is_zt'])
            t = f"F佬/{note}" if note != "关注" else "F佬/关注"
            tags.append(t)
            cleaned_manual = t # 记录下来用于去重

        # --- C. 龙虎榜逻辑 ---
        if code in context['lhb_codes']:
            is_selected = True
            tags.append("🐉龙虎榜")
        if name in context['lhb_seats']:
            is_selected = True
            # 排序: 锁仓/加仓 优先
            def sort_key(t):
                if "🔒" in t or "➕" in t: return 0
                if "💰" in t: return 1
                return 2
            seat_tags = sorted(list(context['lhb_seats'][name]), key=sort_key)
            tags.extend(seat_tags)

        # --- D. 人气逻辑 ---
        is_pop = False
        if code in context['manual'] or name in context['manual']: is_pop = True
        if item['limit_days'] >= 3: is_pop = True
        if item['amount'] > 20_0000_0000: # 20亿
            is_pop = True
            tags.append("成交")
        
        if is_pop:
            is_selected = True
            tags.append("★人气")

        # --- E. 断板反包 (A大焚诀) ---
        if code in context['broken_map'] and item['today_pct'] > 0:
            is_selected = True
            t = "🔥A大焚诀"
            yest_amt = context['broken_map'][code]['amount']
            if item['amount'] > yest_amt and yest_amt > 1000:
                t += "/爆量"
            tags.append(t)

        # --- F. DDD 模式 ---
        ddd_tag = get_ddd_pool_category(item)
        if ddd_tag:
            is_selected = True
            tags.append(ddd_tag)

        # --- G. 历史回溯 (F佬模型) ---
        if code in context['history']:
            f_tags = check_fen_jue(context['history'][code])
            if f_tags:
                tags.extend(f_tags)
                is_selected = True

        # --- H. 筹码分析 (针对重点股) ---
        # 触发条件: 持仓 or 炸板反包 or 3板以上
        should_analyze = (code in context['holdings']) or \
                         (code in context['broken_map']) or \
                         (item['limit_days'] >= 3)
        
        if is_selected and should_analyze:
            met = get_chip_metrics(code)
            if met:
                ct = generate_chip_tag(met)
                if ct: tags.append(ct)

        # ================= 数据增强与合并 =================
        if is_selected:
            # 1. 概念提取 (去重)
            core_concepts = PoolTagger._get_core_concepts(name, item['zt_reason'])
            uniq_concepts = PoolTagger._get_unique_concepts(cleaned_manual, core_concepts)
            
            # 2. 特殊形态 (一字/T字)
            zt_type = ""
            if item['is_zt']:
                if item['open_pct'] > 9.0:
                    zt_type = "一字" if item['open_num'] == 0 else "T字"
                else:
                    zt_type = "换手板"
                tags.append(f"[{zt_type}]")

            # 3. 竞价占比 (Call Auction Ratio)
            y_amt = 0
            if context['yest_full'] and code in context['yest_full']:
                y_amt = context['yest_full'][code].get('amount', 0)
            
            ratio = round(item['call_auction_amount'] / y_amt, 3) if y_amt > 0 else 0
            
            # 4. 标签最终合并
            final_tags = []
            final_tags.extend(tags)
            if uniq_concepts: final_tags.append(uniq_concepts)
            
            # 列表去重
            seen = set()
            clean_tags = [x for x in final_tags if not (x in seen or seen.add(x))]
            
            # 5. 风险数据注入
            risk_info = context['risk_map'].get(name, {
                'risk_level': '🟢 Safe', 'risk_msg': '-', 'trigger_next': '-', 'risk_rule': '-',
                'deviation_val_10d': 0.0, 'deviation_val_30d': 0.0
            })

            # 构造最终输出对象
            item.update({
                'tag': "/".join(clean_tags).replace('//', '/'),
                'sina_code': PoolTagger._format_sina(code),
                'link_dragon': context['link_dragon_map'].get(code, ''),
                'last_amount': y_amt,
                'call_auction_ratio': ratio,
                'limit_up_type': zt_type,
                # 风险字段
                'risk_level': risk_info['risk_level'],
                'risk_msg': risk_info['risk_msg'],
                'risk_rule': risk_info['risk_rule'],
                'trigger_next': risk_info['trigger_next'],
                'deviation_val_10d': risk_info['deviation_val_10d'],
                'deviation_val_30d': risk_info['deviation_val_30d']
            })
            
            return True, item
            
        return False, item

    # --- 内部辅助方法 ---

    @staticmethod
    def _clean_manual_tag(tag, is_zt):
        if not tag: return ""
        tag = tag.replace('F佬/', '').replace('F佬', '')
        # 如果当前是涨停，移除旧的手动"x板"标签，避免混淆
        if is_zt: tag = re.sub(r'(^|/|[(])\d+板([)]|/|$)', r'\1\2', tag)
        tag = tag.replace('()', '').replace('//', '/').strip('/')
        return tag

    @staticmethod
    def _get_unique_concepts(base, new_con):
        """确保新概念不包含在手动备注里"""
        if not new_con: return ""
        base_parts = set(re.split(r'[/()]', base))
        final = [c for c in new_con.split('/') if c and c not in base_parts and c not in base]
        return "/".join(final)

    @staticmethod
    def _get_core_concepts(name, reason_text):
        """从名称和原因中提取核心题材"""
        text = f"{name} {reason_text}"
        found = [k for k in CORE_KEYWORDS if k in text]
        return "/".join(found)

    @staticmethod
    def _format_sina(code):
        if code.startswith('6'): return f"sh{code}"
        return f"sz{code}"