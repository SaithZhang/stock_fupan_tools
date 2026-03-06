# src/core/stock_tagger.py

from src.utils.text_tools import TextUtils
from src.data.market import TechnicalAnalyzer


class StockTagger:
    def __init__(self, top_amount_threshold):
        self.top_amount_threshold = top_amount_threshold

    def get_tags(self, item, strategies_hit_tags):
        """
        统一处理单只股票的所有打标逻辑
        """
        hit_tags = list(strategies_hit_tags)  # 复制一份策略命中的标签
        code = item.get('code', '')
        name = item.get('name', '')
        is_zt = item.get('is_zt', False)

        # ✅ 新增：记录是否需要强制入选底层池
        force_select = False

        # A. 涨停连板标签
        if is_zt:
            limit_days = item.get('limit_days', 1)
            hit_tags.append(f"{limit_days}板")

        # B. 同花顺概念融合
        ths_desc = item.get('ths_desc', '')
        if ths_desc:
            concepts = ths_desc.split('+')
            cleaned_concepts = "/".join(concepts[:2])
            hit_tags.append(cleaned_concepts)

        # C. 实时炸板识别
        if item.get('is_broken'):
            hit_tags.append("💣炸板")

        # D. 竞价逻辑分析 (精细化防雷与防误导)
        auc_ratio = item.get('auction_ratio', 0.0)
        auc_amt = item.get('auc_amt', 0)
        # 兼容处理：尝试获取竞价涨幅，如果没有则用开盘涨幅兜底
        auc_pct = item.get('auc_pct', item.get('open_pct', 0.0))
        yest_pct = item.get('yest_pct', item.get('today_pct', 0.0))  # 昨天涨幅(若为复盘当日，即为当日涨幅的上一日)

        # 1. 绝对金额过亿，主力入场标志
        if auc_amt > 100000000:
            hit_tags.append("💰竞价过亿")

        # 2. 竞价达标与超预期 (设置绝对门槛：至少1000万以上才有资格谈量比)
        if auc_amt >= 10000000:
            if auc_ratio >= 0.10:
                if auc_pct > 0:
                    # 只有高开(红盘)，且结合昨日弱势/分歧，才是真正的超预期
                    if yest_pct < 5.0 and auc_pct > 1.5:
                        hit_tags.append("🔥竞价超预期")
                    else:
                        hit_tags.append("🔥竞价爆量抢筹")  # 涨幅不够大或昨天已经很强，只能叫爆量
                elif auc_pct < -2.0:
                    # 水下爆量，这是核按钮抢跑的危险信号
                    hit_tags.append("💣竞价爆量砸盘")
            elif auc_ratio >= 0.05 and auc_pct > 0:
                hit_tags.append("⚡竞价达标")

        # 3. 弱转强判定 (昨弱今强)
        # 昨天没涨停（甚至大分歧），今天高开有量
        if auc_ratio >= 0.05 and auc_pct >= 1.5 and yest_pct < 4.0:
            hit_tags.append("🎯疑似弱转强")
        elif auc_ratio >= 0.05 and is_zt:
            hit_tags.append("🎯涨停承接达标")

        # E. 人气/容量兜底
        is_capacity_stock = (item.get('amount', 0) > self.top_amount_threshold) and (item.get('today_pct', 0) > 0)
        if is_capacity_stock: hit_tags.append("★人气/容量")

        # F. 补充本地概念与形态
        local_concepts = TextUtils.get_core_concepts_local(name, str(item.get('tag', '')))
        if local_concepts: hit_tags.append(local_concepts)

        shape_tags, zt_type = TechnicalAnalyzer.check_special_shape(item)
        if zt_type: hit_tags.append(f"[{zt_type}]")
        hit_tags.extend(shape_tags)

        # =====================================================================
        # G. 🔥 老龙横盘特征识别 (L大：空间压制下的老龙头破局形态)
        # =====================================================================
        # 1. 曾经是高标空间龙（近15个交易日内，最大连板数 >= 3）
        recent_max_boards = item.get('recent_max_boards', 0)

        # 2. 近期断板但横盘抗跌（近3天没涨停，且最高点回撤极小，比如小于15%）
        days_since_last_zt = item.get('days_since_last_zt', 99)
        drawdown_from_high = item.get('drawdown_from_high', 100.0)

        # 3. 趋势支撑（稳在10日线上）
        close_price = item.get('price', 0.0)  # to_dict中导出的是price
        ma10 = item.get('ma10', 0.0)

        is_old_dragon = recent_max_boards >= 3
        is_sideways = (days_since_last_zt >= 3) and (drawdown_from_high < 15.0)
        is_trend_intact = (close_price > ma10) and (ma10 > 0)

        # 满足三个条件，打上高贵的老龙标签
        if is_old_dragon and is_sideways and is_trend_intact:
            hit_tags.append("[老龙横盘]")
            force_select = True  # 触发此模式必须无脑送入底层监控池
        # =====================================================================

        # 返回去重后的标签字符串和是否选中的标志
        final_tag_str = "/".join(sorted(list(set(hit_tags)))).replace('//', '/')

        # 判定是否入选 (✅ 增加 force_select 判定)
        is_selected = False
        if force_select:
            is_selected = True
        elif item.get('limit_days', 0) >= 1 or is_zt:
            is_selected = True
        elif item.get('is_broken'):
            is_selected = True
        elif strategies_hit_tags:
            is_selected = True  # 如果策略命中了，也入选
        elif is_capacity_stock:
            is_selected = True

        return final_tag_str, is_selected, zt_type