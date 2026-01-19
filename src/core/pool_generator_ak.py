# ==============================================================================
# 🎮 策略池生成器入口 (src/core/pool_generator_ak.py)
# 作用: 调度 DataSource 和 Tagger，生成最终的 CSV 和 JSON
# ==============================================================================
import os
import sys
import shutil
import json
import pandas as pd
from datetime import datetime
from colorama import init, Fore

# --- 1. 路径修复 (防止找不到模块) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- 2. 模块导入 ---
from src.config.pool_config import OUTPUT_DIR, ARCHIVE_DIR, LINK_DRAGON_MAP
from src.core.pool_data_source import PoolDataSource
from src.core.pool_tagger import PoolTagger

init(autoreset=True)

def run_generator():
    print(f"{Fore.CYAN}🚀 开始生成策略池 (模块化版)...")
    
    # 1. 准备数据源
    loader = PoolDataSource()
    all_data = loader.get_base_market_data()
    
    if not all_data:
        print(f"{Fore.RED}❌ 无法获取基础数据，程序终止")
        return

    # 2. 加载上下文 (一次性加载所有依赖数据)
    holdings, flao, manual = loader.load_text_lists()
    lhb_codes, lhb_seats = loader.load_lhb_data()
    md_manager, market_loaded = loader.load_market_sentiment()
    
    context = {
        'holdings': holdings,
        'flao': flao,
        'manual': manual,
        'lhb_codes': lhb_codes,
        'lhb_seats': lhb_seats,
        'risk_map': loader.load_risk_data(),
        'broken_map': loader.load_yesterday_broken_pool(),
        'history': loader.load_history_data(days=5),
        'yest_full': loader.load_yesterday_full(),
        'link_dragon_map': LINK_DRAGON_MAP
    }
    
    print(f"{Fore.GREEN}📋 数据准备完毕 | 股票: {len(all_data)} | 持仓: {len(holdings)} | 关注: {len(flao)}")

    # 3. 核心循环 (调用 Tagger)
    pool = []
    market_stats = {
        'limit_up_count': 0, 
        'limit_down_count': 0, 
        'highest_space': 0
    }
    
    for item in all_data:
        # 统计大盘数据 (无论是否入选)
        if item['is_zt'] or item['today_pct'] > 9.8: 
            market_stats['limit_up_count'] += 1
            if item['limit_days'] > market_stats['highest_space']:
                market_stats['highest_space'] = item['limit_days']
        if item['today_pct'] < -9.0:
            market_stats['limit_down_count'] += 1

        # 核心筛选
        is_selected, enriched_item = PoolTagger.process(item, context)
        if is_selected:
            pool.append(enriched_item)

    # 4. 导出 CSV
    if pool:
        _export_csv(pool)
    else:
        print(f"{Fore.YELLOW}⚠️ 未筛选出任何标的")

    # 5. 导出 JSON (大盘情绪)
    if market_loaded:
        _export_json(md_manager, market_stats, context['yest_full'], all_data)


def _export_csv(pool_data):
    """导出 CSV 文件"""
    df = pd.DataFrame(pool_data)
    df.sort_values(by='amount', ascending=False, inplace=True)
    
    # 定义输出列顺序
    cols = ['sina_code', 'name', 'tag', 'amount', 'today_pct', 'turnover', 'open_pct', 'price', 
            'risk_level', 'risk_msg', 'trigger_next', 'risk_rule', 'deviation_val_10d', 'deviation_val_30d',
            'call_auction_ratio', 'last_amount', 'limit_up_type', 'vol_ratio', 'link_dragon', 'code']
    
    # 过滤掉不存在的列
    final_cols = [c for c in cols if c in df.columns]
    df = df[final_cols]
    
    today_str = datetime.now().strftime("%Y%m%d")
    out_file = os.path.join(OUTPUT_DIR, f'strategy_pool_{today_str}.csv')
    
    df.to_csv(out_file, index=False, encoding='utf-8-sig')
    shutil.copyfile(out_file, os.path.join(OUTPUT_DIR, 'strategy_pool.csv'))
    
    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
    shutil.copy2(out_file, os.path.join(ARCHIVE_DIR, f'strategy_pool_{today_str}.csv'))
    
    print(f"{Fore.GREEN}✅ 策略池生成完毕: {out_file} ({len(pool_data)}只)")


def _export_json(md_manager, stats, yest_data, all_data):
    """导出前端大盘 JSON"""
    today_str = datetime.now().strftime("%Y%m%d")
    
    # 计算昨日涨停溢价
    total_prem = 0
    valid_count = 0
    yest_zt_codes = [c for c, v in yest_data.items() if v.get('is_zt')]
    for c in yest_zt_codes:
        curr = next((x for x in all_data if x['code'] == c), None)
        if curr:
            total_prem += curr.get('open_pct', 0)
            valid_count += 1
    
    avg_prem = round(total_prem / valid_count, 2) if valid_count > 0 else 0
    stats['yesterday_limit_up_premium'] = avg_prem

    # 合并数据
    final_json = md_manager.get_summary()
    final_json.update(stats)
    
    out_path = os.path.join(OUTPUT_DIR, f'market_sentiment_{today_str}.json')
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(final_json, f, indent=2, ensure_ascii=False)
        print(f"📄 大盘数据导出: {out_path}")
    except Exception as e:
        print(f"{Fore.RED}❌ 导出JSON失败: {e}")

if __name__ == '__main__':
    run_generator()