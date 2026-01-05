import pandas as pd
import os
import shutil
import sys
import re
from datetime import datetime
from colorama import init, Fore

# --- 导入修复 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from .data_loader import get_merged_data
except ImportError:
    from data_loader import get_merged_data
# --------------

init(autoreset=True)

PROJECT_ROOT = os.path.dirname(os.path.dirname(current_dir))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

HOLDINGS_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'holdings.txt')
F_LAO_PATH = os.path.join(PROJECT_ROOT, 'data', 'input', 'f_lao_list.txt')


def load_text_list(filepath):
    if not os.path.exists(filepath): return {}
    mapping = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            code_match = re.search(r'\d{6}', line)
            if code_match:
                code = code_match.group()
                mapping[code] = line
    return mapping


def generate_strategy_pool():
    all_data = get_merged_data()
    if not all_data: return

    holdings_map = load_text_list(HOLDINGS_PATH)
    focus_map = load_text_list(F_LAO_PATH)

    print(f"{Fore.CYAN}📋 加载名单: 持仓 {len(holdings_map)} 只, 关注 {len(focus_map)} 只")

    pool = []
    print(f"\n{Fore.YELLOW}🚀 开始执行筛选 (严格模式: 涨停 + 大战场 + 跌停观测)...{Fore.RESET}")

    kept_count = 0

    for item in all_data:
        code = item['code']
        raw_tag = str(item.get('tag', ''))
        name = item['name']
        pct = item['today_pct']

        # 修复标签中出现的 'nan'
        if 'nan' in raw_tag:
            raw_tag = raw_tag.replace('nan/', '').replace('/nan', '').replace('nan', '')

        tags = []
        is_keep = False
        debug_reason = ""

        # ================= 筛选逻辑 =================

        # 1. 持仓 (优先级最高)
        if code in holdings_map:
            is_keep = True
            tags.append("持仓")
            debug_reason = "持仓"

        # 2. 关注 (优先级次高)
        if code in focus_map:
            is_keep = True
            note = focus_map[code].replace(code, '').strip()
            tags.append(f"F佬/{note}" if note else "F佬/关注")
            if not debug_reason: debug_reason = "F佬关注"

        # 3. 涨停/连板 (红盘且是API确认的涨停 或 涨幅够大)
        is_real_zt = item.get('is_zt') and pct > 0
        is_high_pct = pct > 9.5

        if is_real_zt or is_high_pct:
            if not is_keep:
                is_keep = True
                debug_reason = f"涨停(pct={pct:.2f})"

            if raw_tag:
                tags.append(raw_tag)
            elif item.get('limit_days', 0) > 0:
                tags.append(f"{item['limit_days']}板")
            else:
                tags.append("首板")

        # 4. 炸板 (跌幅>-7%的才算炸板，深水算核按钮)
        if "炸板" in raw_tag or item.get('tag_extra') == '炸板':
            if pct > -7.0:
                if not is_keep:
                    is_keep = True
                    debug_reason = f"炸板(pct={pct:.2f})"
                tags.append("炸板/反包预期")

        # 5. 资金战场 (20亿+ 且 红盘)
        amount_yi = item.get('amount', 0) / 100000000.0
        if amount_yi > 20.0 and pct > 0:
            if not is_keep:
                is_keep = True
                debug_reason = f"大战场(额={amount_yi:.1f}亿)"
            tags.append("💰大战场")

        # 6. 地天板 (绿盘开，红盘收，大长腿)
        if pct > 5.0 and item.get('open_pct', 0) < -4.0:
            if not is_keep:
                is_keep = True
                debug_reason = "地天板"
            tags.append("🔥大长腿")

        # 7. [新增] 跌停/核按钮 (跌幅 < -9.0%)
        # 关注跌停是为了看情绪退潮和潜在的反核机会
        if pct < -9.0:
            if not is_keep:
                is_keep = True
                debug_reason = f"跌停(pct={pct:.2f})"
            tags.append("📉跌停/核按钮")

        # ================= 最终生成 =================
        if is_keep:
            # 清洗 Tag
            final_tag_str = "/".join(list(dict.fromkeys(tags)))

            # 过滤空 Tag (除非是纯涨停/跌停)
            # if not final_tag_str and not is_high_pct: continue

            # 日志 (只显示非持仓/非关注的)
            if "持仓" not in final_tag_str and "F佬" not in final_tag_str:
                print(f"   [入池] {code} {name[:4]} | 涨幅:{pct:>6.2f}% | 原因: {debug_reason}")

            sina_code = item.get('sina_code')
            if not sina_code:
                prefix = "sh" if code.startswith(('6', '9')) else "sz"
                sina_code = f"{prefix}{code}"

            row = {
                'sina_code': sina_code,
                'name': name,
                'tag': final_tag_str,
                'amount': item.get('amount', 0),
                'today_pct': pct,
                'turnover': item['turnover'],
                'open_pct': item.get('open_pct', 0.0),
                'price': item['price'],
                'pct_10': item.get('pct_10', 0.0),
                'link_dragon': '',
                'vol': 0, 'vol_prev': 0, 'vol_ratio': 0,
                'code': code
            }
            pool.append(row)
            kept_count += 1

    # --- 导出 ---
    if pool:
        df = pd.DataFrame(pool)

        # 排序策略 (Sort Key)
        # 分数越高排越前
        def get_sort_key(row):
            t = str(row['tag'])
            score = 0
            # 1. 持仓/关注 (最优先)
            if '持仓' in t: score += 10000
            if 'F佬' in t: score += 5000

            # 2. 涨停梯队
            import re
            m = re.search(r'(\d+)板', t)
            if m:
                score += int(m.group(1)) * 100
            elif '首板' in t:
                score += 50
            elif '地天' in t or '大长腿' in t:
                score += 40

            # 3. 炸板 (次之)
            elif '炸板' in t:
                score += 20

            # 4. 跌停 (放在最后，但比普通大战场要显眼一点吗？)
            # 我们给跌停 10分，让它排在 炸板 后面，但在纯大战场前面(0分)
            # 这样你可以先看涨停，再看炸板，再看跌停，最后看大成交额中军
            elif '跌停' in t:
                score += 10

            return score

        df['sort_score'] = df.apply(get_sort_key, axis=1)

        # 排序：先按分数(梯队)，同梯队按成交额
        df.sort_values(by=['sort_score', 'amount'], ascending=[False, False], inplace=True)
        df.drop(columns=['sort_score'], inplace=True)

        cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 'pct_10',
                'link_dragon', 'vol', 'vol_prev', 'vol_ratio', 'code']
        df = df[cols]

        date_str = datetime.now().strftime("%Y%m%d")
        save_path = os.path.join(ARCHIVE_DIR, f'strategy_pool_{date_str}.csv')
        latest_path = os.path.join(OUTPUT_DIR, 'strategy_pool.csv')

        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        shutil.copyfile(save_path, latest_path)

        print(f"\n{Fore.GREEN}🎉 复盘完成！生成标的: {len(pool)} 只 (含跌停观测)")
        print(f"📄 文件已保存: {latest_path}")
    else:
        print(f"{Fore.RED}❌ 结果为空。")


if __name__ == "__main__":
    generate_strategy_pool()