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
    #Top Yu
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
        '天津东丽开发区', '华泰证券股份有限公司天津东丽开发区二纬路', # Also 交易猿
        '深圳深南大道', '深圳分公司' # Sometimes
    ],
    '章盟主': [
        '上海江苏路', '国泰君安证券股份有限公司上海江苏路',
        '宁波江东北路' # 
    ],
    '知春路': ['知春路', '北京知春路'], # Sell 3 in Goldwind
    '养家': [
        '宛平南路', '华鑫证券有限责任公司上海宛平南路',
        '上海茅台路', '华鑫证券有限责任公司上海茅台路',
        '上海松江', '华鑫证券有限责任公司上海松江',
        '上海陆家嘴', '华鑫证券有限责任公司上海陆家嘴',
        '西安二环', '华鑫证券有限责任公司西安二环' # Sometimes used
    ],
    '上塘路': ['上塘路', '财通证券股份有限公司杭州上塘路', '体育馆路', '财通证券股份有限公司杭州体育馆路'],
    '作手新一': [
        '南京太平南路', '国泰君安证券股份有限公司南京太平南路', 
        '南京金融城', 
        '重庆解放碑', '国泰海通证券股份有限公司重庆解放碑', '国泰君安证券股份有限公司重庆解放碑' # User noted, usually Zuoshou
    ],
    '小鳄鱼': ['南京大钟亭', '南京证券股份有限公司南京大钟亭', '上海东方路', '广发证券股份有限公司上海东方路'],
    '毛老板': ['北京北三环东路', '成都南一环路'],
    
    # New Additions
    '92科比': ['泰州鼓楼南路', '国泰君安证券股份有限公司泰州鼓楼南路', '南京天元东路', '兴业证券股份有限公司南京天元东路'],
    '消闲派': ['宜昌珍珠路', '国泰君安证券股份有限公司宜昌珍珠路', '宜昌沿江大道', '国泰海通证券公宜昌沿江大道营业部'], # Added Yanjiang
    '余哥': ['相城大道', '光大证券股份有限公司苏州相城大道', '东吴证券股份有限公司苏州相城大道', '宁波沙滩路', '余姚舜水南路', '宁波海晏北路', '平安证券股份有限公司宁波海晏北路'], # Added Soochow Xiangcheng
    '赵老哥': ['绍兴', '中国银河证券股份有限公司绍兴', '绍兴解放北路'],
    '中山东路': ['中山东路', '上海松江区中山东路', '国泰海通证券上海松江区中山东路营业部'], # New from news
    '宁波桑田路': ['宁波桑田路', '国盛证券有限责任公司宁波桑田路'],
    '佛山系': ['佛山绿景路', '光大证券股份有限公司佛山绿景路', '佛山季华六路'],
    '和平路': ['鞍山和平路', '中信证券股份有限公司鞍山和平路'], # Big buyer usually
    '交易猿': ['天津东丽开发区', '华泰证券股份有限公司天津东丽开发区二纬路'], # Often same as 61
    '思明南路': ['东莞证券股份有限公司湖北分公司', '东亚前海证券有限责任公司上海分公司'],
    
    # Groups
    '拉萨天团': [
        '拉萨团结路', '东方财富证券股份有限公司拉萨团结路',
        '拉萨东环路', '东方财富证券股份有限公司拉萨东环路',
        '拉萨金融城', '东方财富证券股份有限公司拉萨金融城'
    ],
    '北向': ['深股通', '沪股通', '香港中央结算有限公司'],
    '机构': ['机构专用']
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
                # Fix: Must fetch both '买入' and '卖出' lists to get complete data
                try:
                    df_buy = ak.stock_lhb_stock_detail_em(symbol=code, date=date_str, flag="买入")
                    df_sell = ak.stock_lhb_stock_detail_em(symbol=code, date=date_str, flag="卖出")
                    
                    df_detail = pd.concat([df_buy, df_sell], ignore_index=True)
                    # Deduplicate based on Branch and Type (as one branch might appear in multiple list types, e.g., 3-day and 1-day)
                    # But merging duplicates with same values is fine. 
                    # Warning: valid to have same branch in 1-day AND 3-day list (different '类型'). 
                    # If same branch/type appears in buy and sell list, it is identical.
                    df_detail = df_detail.drop_duplicates(subset=['交易营业部名称', '类型'])
                    
                except Exception as e:
                    # print(f"Error fetching detail for {code}: {e}")
                    continue

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
                    branch = branch.strip()
                    
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
                                
                                # 解析榜单类型 (日榜 vs 3日榜)
                                lhb_type = row.get('类型', '')
                                time_tag = "日" # Default
                                if "三" in lhb_type or "3" in lhb_type:
                                    time_tag = "3日"
                                elif "严重" in lhb_type: # 严重异常波动 usually covers longer period (e.g. 10 days) or specific check
                                    time_tag = "严重异动"
                                
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
                                    '卖出金额': sell_amt,
                                    '榜单标签': time_tag
                                })
                                break # Match one label only
            except Exception as e:
                # print(f"Error scanning {code}: {e}")
                continue
                
        # --- Locking Position Detection (Suocang) ---
        # Logic: If (Seat, Stock) in Yesterday's Famous Buy List AND Stock in Today's LHB AND Seat NOT in Today's Sell List -> Locked
        
        try:
            # 1. Find previous famous file
            # Simple lookback for now
            import datetime as dt
            curr_date = datetime.strptime(date_str, "%Y%m%d")
            prev_file = None
            for i in range(1, 5): # Check back 4 days for previous trading day
                prev_d_str = (curr_date - dt.timedelta(days=i)).strftime("%Y%m%d")
                p_path = os.path.join(LHB_DIR, f"lhb_famous_{prev_d_str}.csv")
                if os.path.exists(p_path):
                    prev_file = p_path
                    print(f"   🔍 对比昨日数据: {prev_d_str}")
                    break
            
            if prev_file:
                df_prev = pd.read_csv(prev_file)
                # Prepare today's sell set: {(Label, Stock)}
                today_sell_set = set()
                for h in hits:
                    if "卖" in h['操作'] or "做T" in h['操作']:
                        today_sell_set.add((h['游资标签'], h['股票名称']))
                
                # Check previous buys
                for _, row in df_prev.iterrows():
                    p_label = row['游资标签']
                    p_buys = str(row['买入股票'])
                    if pd.isna(p_buys) or not p_buys.strip(): continue
                    
                    # Buy string might be "StockA StockB(1.2亿)"
                    import re
                    # Extract stock names from "StockA(1亿) StockB"
                    # Simple split by space
                    p_stocks_raw = p_buys.split(' ')
                    for s_raw in p_stocks_raw:
                        if not s_raw: continue
                        # Remove amount info like (1.2亿)
                        s_name = re.sub(r'\(.*?\)', '', s_raw)
                        s_name = s_name.strip()
                        
                        # Check if this stock is in TODAY'S LHB List (df_lhb)
                        if s_name in df_lhb['名称'].values:
                            # Start check
                            has_sold = (p_label, s_name) in today_sell_set
                            has_bought_today = False
                            for h in hits:
                                if h['游资标签'] == p_label and h['股票名称'] == s_name and ("买" in h['操作'] or "做T" in h['操作']):
                                    has_bought_today = True
                                    
                            if not has_sold:
                                status = "🔒 锁仓"
                                if has_bought_today:
                                    status = "➕ 加仓" # Bought and didn't sell
                                
                                already_recorded = False
                                for h in hits:
                                    if h['游资标签'] == p_label and h['股票名称'] == s_name:
                                        # Update existing hit special status if needed, but easier to just skip adding duplicative "Lock" entry
                                        # Only add if completely missing from today's active list
                                        already_recorded = True 
                                        break
                                        
                                if not already_recorded:
                                    hits.append({
                                        '游资标签': p_label,
                                        '营业部名称': f"{p_label}席位(推测)",
                                        '股票代码': "", 
                                        '股票名称': s_name,
                                        '操作': status,
                                        '买入金额': 0,
                                        '卖出金额': 0,
                                        '榜单标签': "日" # Lock means checking against today's status, usually implies keeping daily position
                                    })
        except Exception as e:
            print(f"Error checking locks: {e}")

        # 整理输出
        if hits:
            # Aggregation v2:
            # 1. Group by (Label, Branch, Stock, Tag) -> Take MAX amounts (Dedup 1-day/3-day for same branch IF SAME TAG)
            # 2. Group by (Label, Stock, Tag) -> SUM amounts (Combine multiple branches for same investor)
            
            # Step 1: Branch Level Max (Per Tag)
            # If a branch appears in Daily list, we take its max for Daily.
            # If it appears in 3-Day list, we take its max for 3-Day.
            branch_map = {} # (Label, Branch, Stock, Tag) -> {'buy': max_b, 'sell': max_s, 'status': s}
            
            for h in hits:
                lbs_key = (h['游资标签'], h['营业部名称'], h['股票名称'].strip(), h['榜单标签'])
                if lbs_key not in branch_map:
                    branch_map[lbs_key] = {'buy': 0, 'sell': 0, 'special_status': None}
                
                curr = branch_map[lbs_key]
                curr['buy'] = max(curr['buy'], h['买入金额'])
                curr['sell'] = max(curr['sell'], h['卖出金额'])
                if "锁仓" in h['操作'] or "加仓" in h['操作']:
                    curr['special_status'] = h['操作']

            # Step 2: Investor Level Sum (Per Tag)
            final_map = {} # (Label) -> { (Stock, Tag): {'buy': sum_b, 'sell': sum_s, 'status': ...} }
            
            for (label, branch, stock, tag), vals in branch_map.items():
                if label not in final_map: final_map[label] = {}
                st_key = (stock, tag)
                if st_key not in final_map[label]: final_map[label][st_key] = {'buy': 0, 'sell': 0, 'statuses': set()}
                
                f_curr = final_map[label][st_key]
                f_curr['buy'] += vals['buy']
                f_curr['sell'] += vals['sell']
                if vals['special_status']:
                    f_curr['statuses'].add(vals['special_status'])
            
            # Step 3: Format Rows
            final_rows = []
            for label, item_dict in final_map.items():
                buy_strs = []
                sell_strs = []
                
                # Sort items: First by Stock Name, then by Tag (Daily before 3-Day)
                # item_dict keys are (Stock, Tag)
                sorted_keys = sorted(item_dict.keys(), key=lambda x: (x[0], x[1] != '日')) # '日' comes first
                
                for s_name, tag in sorted_keys:
                    vals = item_dict[(s_name, tag)]
                    b_amt = vals['buy']
                    s_amt = vals['sell']
                    
                    s_display = s_name
                    # Append Tag if not '日'
                    if tag != '日':
                        s_display += f"/{tag}"
                        
                    if vals['statuses']:
                        # prioritizing Lock status display
                        status_str = "/".join(list(vals['statuses']))
                        s_display = f"{s_display}({status_str})"
                    
                    # Formatting check: Show if Buy > 100k OR if "Lock" status (even if buy=0)
                    has_buy_sig = b_amt > 100000
                    has_sell_sig = s_amt > 100000
                    is_special = len(vals['statuses']) > 0
                    
                    if has_buy_sig or (is_special and "锁仓" not in str(vals['statuses'])): 
                        amt_str = ""
                        if b_amt > 100000:
                            amt_str = f"({b_amt/10000:.0f}万)"
                            if b_amt > 100000000:
                                amt_str = f"({b_amt/100000000:.1f}亿)"
                        
                        buy_strs.append(f"{s_display}{amt_str}")

                    elif is_special and "锁仓" in str(vals['statuses']):
                        buy_strs.append(f"{s_display}")

                    if has_sell_sig:
                        amt_str = f"({s_amt/10000:.0f}万)"
                        if s_amt > 100000000:
                            amt_str = f"({s_amt/100000000:.1f}亿)"
                        sell_strs.append(f"{s_display}{amt_str}")

                if not buy_strs and not sell_strs:
                    continue
                
                final_rows.append({
                    '游资标签': label,
                    '营业部名称': "多席位/聚合", 
                    '买入股票': " ".join(buy_strs),
                    '卖出股票': " ".join(sell_strs),
                    '上榜次数': len(buy_strs) + len(sell_strs)
                })

            # Sort by Label
            final_rows.sort(key=lambda x: x['游资标签'])
            
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


def get_recent_trade_dates(days=5):
    """
    获取最近 N 个交易日 (包括今天如果今天也是交易日)
    返回格式: ['20230101', '20230102', ...] (从旧到新)
    """
    try:
        # fetch trade dates
        df = ak.tool_trade_date_hist_sina()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        today = datetime.now().date()
        # Filter dates <= today
        past_dates = df[df['trade_date'].dt.date <= today]
        
        if past_dates.empty:
            return [today.strftime("%Y%m%d")]

        # Get last N dates
        recent = past_dates.iloc[-days:]['trade_date'].dt.strftime("%Y%m%d").tolist()
        return recent
    except Exception as e:
        print(f"{Fore.RED}⚠️ 获取交易日历失败: {e}")
        # Fallback: return today and yesterday
        today_str = datetime.now().strftime("%Y%m%d")
        from datetime import timedelta
        yest_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        return [yest_str, today_str]

if __name__ == "__main__":
    # 智能查找最近的龙虎榜数据
    # 策略: 获取最近 3 个交易日，倒序查找 (最新 -> 最旧)
    # 这样可以处理周末、节假日、晚间未更新等情况
    
    print(f"{Fore.CYAN}📅 正在确定最近的交易日数据...")
    
    candidates = get_recent_trade_dates(days=3)
    # Reverse to check latest first
    candidates.reverse()
    
    found_date = None
    
    for date_str in candidates:
        print(f"   👉 尝试日期: {date_str}")
        df = fetch_lhb_data(date_str)
        if df is not None and not df.empty:
            found_date = date_str
            process_and_save(df, date_str)
            fetch_famous_seats(date_str)
            break
            
    if not found_date:
        print(f"{Fore.RED}❌ 最近 3 个交易日均未获取到数据，请检查网络或稍后再试。")

