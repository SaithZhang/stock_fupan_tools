import akshare as ak
import pandas as pd
import os
import shutil
from datetime import datetime
from colorama import init, Fore

init(autoreset=True)

# 路径配置
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
LHB_DIR = os.path.join(OUTPUT_DIR, 'lhb') # New dedicated folder
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, 'archive')

# 知名游资/席位映射配置
# 格式: '游资标签': ['关键词1', '关键词2']
# 知名游资/席位映射配置
# 格式: '游资标签': ['关键词1', '关键词2']
FAMOUS_SEATS = {
    '陈小群': [
        '大连金马路', '中国银河证券股份有限公司大连金马路',
        '大连黄河路', '中国银河证券股份有限公司大连黄河路',
        '苏州留园路', '东亚前海证券有限责任公司苏州留园路'
    ],
    '呼家楼': [
        '呼家楼', '中信证券股份有限公司北京呼家楼',
        '北京中信大厦', '中信建投证券股份有限公司北京中信大厦',
        '上海凯滨路', '中信证券股份有限公司上海凯滨路',
        '北京东城分公司', '中信建投证券股份有限公司北京东城分公司',
        '北京广渠门内大街', '中信建投证券股份有限公司北京广渠门内大街',
        '北京总部', '中信证券股份有限公司北京总部',
        '北京建外大街', '广发证券股份有限公司北京建外大街'
    ],
    '方新侠': [
        '西安朱雀大街', '中信证券股份有限公司西安朱雀大街',
        '陕西分公司', '兴业证券股份有限公司陕西分公司',
        '西安曲江池南路', '国投证券股份有限公司西安曲江池南路'
    ],
    '六一中路': [
        '福州六一中路', '招商证券股份有限公司福州六一中路',
        '天津东丽开发区', '华泰证券股份有限公司天津东丽开发区二纬路'
    ],
    '章盟主': [
        '上海江苏路', '国泰君安证券股份有限公司上海江苏路', # 原"六路"
        '宁波江东北路'
    ],
    '养家': ['宛平南路', '华鑫证券有限责任公司上海宛平南路'],
    '上塘路': ['上塘路', '财通证券股份有限公司杭州上塘路'],
    '作手新一': ['南京太平南路', '国泰君安证券股份有限公司南京太平南路'],
    '小鳄鱼': ['南京大钟亭', '南京证券股份有限公司南京大钟亭'],
    '毛老板': ['北京北三环东路', '成都南一环路'],
}

# 确保目录存在
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LHB_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)


def fetch_famous_seats(date_str=None):
    """
    获取知名游资活跃数据 (通过遍历当日龙虎榜标的详情)
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
        
    print(f"{Fore.MAGENTA}🕵️ 开始追踪知名游资 (深度扫描): {date_str}")
    
    # 1. 读取当日龙虎榜标的列表
    lhb_file = os.path.join(LHB_DIR, f"lhb_{date_str}.csv")
    if not os.path.exists(lhb_file):
        print(f"{Fore.YELLOW}⚠️ 未找到当日龙虎榜基础数据，请先运行 fetch_lhb_data")
        return

    try:
        df_lhb = pd.read_csv(lhb_file, dtype={'代码': str})
        if df_lhb.empty: return
        
        codes = df_lhb['代码'].unique().tolist()
        print(f"   📋 待扫描标的: {len(codes)} 只")
        
        hits = [] # {游资, 营业部, 股票, 操作, 金额}
        
        from tqdm import tqdm
        for code in tqdm(codes, desc="Scanning Seats"):
            try:
                # 获取个股详情
                # stock_lhb_stock_detail_em: 东方财富-个股龙虎榜详情
                df_detail = ak.stock_lhb_stock_detail_em(symbol=code, date=date_str)
                if df_detail.empty: continue
                
                # Check columns to ensure we access correctly
                # Expected: 营业部名称, 买入金额, 卖出金额 (values usually in float or string)
                if code == "002413":
                    print(f"DEBUG {code} COLUMNS:", df_detail.columns.tolist())
                    print(df_detail.head(2)) 
                
                stock_name = df_lhb[df_lhb['代码'] == code]['名称'].values[0]
                
                for _, row in df_detail.iterrows():
                    # Column name might be '营业部名称' or '交易营业部名称'
                    branch = str(row.get('营业部名称') or row.get('交易营业部名称', ''))
                    
                    # Amt might be string with commas
                    try:
                        buy_amt = float(row.get('买入金额', 0))
                    except: buy_amt = 0
                    
                    try:
                        sell_amt = float(row.get('卖出金额', 0))
                    except: sell_amt = 0
                    
                    # 匹配知名游资
                    for label, keywords in FAMOUS_SEATS.items():
                        for kw in keywords:
                            if kw in branch:
                                # 命中
                                action_type = "观望"
                                
                                # 阈值调整: 避免微量买入被误判为做T
                                # 1. 显著性判断
                                is_buy_sig = buy_amt > 100000  # 10万
                                is_sell_sig = sell_amt > 100000 # 10万
                                
                                if is_buy_sig and not is_sell_sig:
                                    action_type = "买入"
                                elif is_sell_sig and not is_buy_sig:
                                    action_type = "卖出"
                                elif is_buy_sig and is_sell_sig:
                                    # 双向都有，看比例
                                    if buy_amt > sell_amt * 5:
                                        action_type = "买入" # 买入远大于卖出
                                    elif sell_amt > buy_amt * 5:
                                        action_type = "卖出" # 卖出远大于买入 (如 陈小群卖雷科 1.1亿 vs 买 200万)
                                    else:
                                        action_type = "做T"
                                else:
                                    action_type = "观望"
                                
                                hits.append({
                                    '游资标签': label,
                                    '营业部名称': branch,
                                    '股票代码': code,
                                    '股票名称': stock_name,
                                    '操作': action_type,
                                    '买入金额': buy_amt,
                                    '卖出金额': sell_amt
                                })
                                break # Match one label only
            except Exception as e:
                # print(f"Error scanning {code}: {e}")
                continue
                
        # 整理输出
        if hits:
            # 聚合为之前的格式: 游资标签, 营业部名称, 买入股票(list), 卖出股票(list)
            # 但为了准确，我们这里可以稍微变通一下，或者还原为之前的格式以便 pool_generator 读取
            
            # Map: { (label, branch) : {'buy': [], 'sell': []} }
            agg_map = {}
            for h in hits:
                key = (h['游资标签'], h['营业部名称'])
                if key not in agg_map: agg_map[key] = {'buy': [], 'sell': []}
                
                s_name = h['股票名称']
                act = h['操作']
                
                if "买" in act or "做T" in act:
                    agg_map[key]['buy'].append(f"{s_name}({h['买入金额']/10000:.1f}亿)" if h['买入金额']>100000000 else s_name)
                if "卖" in act or "做T" in act:
                    agg_map[key]['sell'].append(s_name)
                    
            final_rows = []
            for (label, branch), val in agg_map.items():
                final_rows.append({
                    '游资标签': label,
                    '营业部名称': branch,
                    '买入股票': " ".join(val['buy']),
                    '卖出股票': " ".join(val['sell']),
                    '上榜次数': len(val['buy']) + len(val['sell'])
                })
                
            df_res = pd.DataFrame(final_rows)
            file_path = os.path.join(LHB_DIR, f"lhb_famous_{date_str}.csv")
            df_res.to_csv(file_path, index=False, encoding='utf-8-sig')
            
            latest_path = os.path.join(LHB_DIR, "lhb_famous_latest.csv")
            shutil.copyfile(file_path, latest_path)
            
            print(f"{Fore.GREEN}✅ 深度扫描完成，发现 {len(final_rows)} 个活跃席位")
            # Print preview
            for _, r in df_res.iterrows():
                msg = f"   🔥 [{r['游资标签']}]"
                if r['买入股票']: msg += f" | 买: {r['买入股票']}"
                if r['卖出股票']: msg += f" | 卖: {r['卖出股票']}"
                print(msg)
                
        else:
             print(f"{Fore.CYAN}🤷 无知名游资上榜")

    except Exception as e:
        print(f"{Fore.RED}⚠️ 扫描失败: {e}")


def fetch_lhb_data(date_str=None):
    """
    获取指定日期的龙虎榜详情
    date_str: YYYYMMDD
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
        
    print(f"{Fore.CYAN}🚀 开始获取龙虎榜数据: {date_str}")
    
    try:
        # 使用东方财富接口，数据较全
        # start_date 和 end_date 设置为同一天
        df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
        
        if df.empty:
            print(f"{Fore.RED}❌ 该日期无龙虎榜数据")
            return None
            
        print(f"{Fore.GREEN}✅ 获取成功，共 {len(df)} 条记录 (含同一股票多条上榜记录)")
        return df
        
    except Exception as e:
        print(f"{Fore.RED}⚠️ 获取失败: {e}")
        return None

def process_and_save(df, date_str):
    """
    清洗并保存数据
    """
    if df is None or df.empty: return

    # 1. 简单清洗 / 重命名
    # 原始列通常包含: 序号, 代码, 名称, 解读, 收盘价, 涨跌幅, 龙虎榜净买额, 龙虎榜买入额, 龙虎榜卖出额, 龙虎榜成交额, 市场总成交额, 净买额占总成交比, 成交额占总成交比, 换手率, 上榜原因
    
    # 按照惯例，整理一下列顺序，把重要的放前面
    # 必须存在的列映射 (根据 debug_lhb.py 的观察)
    # 假设 akshare 返回的标准中文列名
    
    # 尝试筛选和排序列
    target_cols = [
        '代码', '名称', '上榜原因', 
        '收盘价', '涨跌幅', '换手率',
        '龙虎榜净买额', '龙虎榜买入额', '龙虎榜卖出额', '龙虎榜成交额',
        '市场总成交额', '净买额占总成交比'
    ]
    
    # 只有存在的列才保留
    available_cols = [c for c in target_cols if c in df.columns]
    df = df[available_cols]
    
    # 排序: 按照 龙虎榜净买额 降序 (注意可能是字符串，需要转换)
    if '龙虎榜净买额' in df.columns:
        # 可能是 numeric 或者是 object，akshare 这个接口通常返回 object 带着单位? 
        # 这里还是做个防错处理
        # 观察 debug 输出，akshare em 接口返回通常是 float
        pass

    # 保存文件
    filename = f"lhb_{date_str}.csv"
    filepath = os.path.join(LHB_DIR, filename)
    
    try:
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"📄 已保存: {filepath}")
        
        # 复制为 latest
        latest_path = os.path.join(LHB_DIR, "lhb_latest.csv")
        shutil.copyfile(filepath, latest_path)
        print(f"📄 已更新: {latest_path}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ 保存文件失败: {e}")

if __name__ == "__main__":
    # 默认跑当天的
    today = datetime.now().strftime("%Y%m%d")
    
    # 如果现在还没收盘(比如上午)，可能没数据，或者只有部分
    # 建议手动指定或者自动跑
    
    df = fetch_lhb_data(today)
    if df is None:
        # 尝试跑昨天的，方便调试
        print(f"{Fore.YELLOW}⚠️ 尝试获取昨日数据作为测试...")
        from datetime import timedelta
        yest = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        df = fetch_lhb_data(yest)
        process_and_save(df, yest)
        fetch_famous_seats(yest)
    else:
        process_and_save(df, today)
        fetch_famous_seats(today)
