import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import time
import random
import json

# ================= 配置区域 (Configuration) =================
# 目标用户的 UID (例如你提供的 150058)
TARGET_UID = "150058"

# Cookie 文件路径
# 优先使用 JSON 格式 (Playwright 生成)
COOKIE_FILE_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                           "output", "nga_cookies.json")
# 兼容旧版 TXT 格式
COOKIE_FILE_TXT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                           "input", "nga_cookies.txt")

# 输出文件路径
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                           "output", f"nga_user_{TARGET_UID}_replies.csv")

# 调试文件路径
DEBUG_HTML_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                           "output", "debug_nga_response.html")

# 检查点文件路径
CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                           "output", "nga_scraper_checkpoint.txt")

# 抓取页数范围
START_PAGE = 1
MAX_PAGE = 200  # 用户要求至少200页

# 每次翻页的等待时间区间 (秒)，防止被封
# 用户提示"抓取太频繁"，增加等待时间
SLEEP_MIN = 6.0
SLEEP_MAX = 12.0

# 重试配置
MAX_RETRIES = 5
RETRY_WAIT_BASE = 60 # 遇到封禁/繁忙时的基础等待时间(秒)

# ===========================================================

def parse_cookies_txt(cookie_content):
    """解析旧版 Cookie 字符串为字典"""
    cookies = {}
    lines = cookie_content.splitlines()
    valid_lines = [line.strip() for line in lines if
                   line.strip() and "Please paste" not in line and "Format:" not in line]
    raw_cookie = "".join(valid_lines)

    for item in raw_cookie.split(';'):
        if '=' in item:
            name, value = item.split('=', 1)
            cookies[name.strip()] = value.strip()
    return cookies

def load_cookies_from_json(json_path):
    """从 JSON 文件加载 Cookies (Playwright 格式)"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cookie_list = json.load(f)
        
        cookies = {}
        for cookie in cookie_list:
            if 'name' in cookie and 'value' in cookie:
                cookies[cookie['name']] = cookie['value']
        return cookies
    except Exception as e:
        print(f"Failed to load JSON cookies: {e}")
        return {}

def scrape_user_replies():
    """抓取特定 UID 的所有回复"""
    # 1. 检查 Cookie
    cookies = {}
    if os.path.exists(COOKIE_FILE_JSON):
        print(f"Loading cookies from JSON: {COOKIE_FILE_JSON}")
        cookies = load_cookies_from_json(COOKIE_FILE_JSON)
    elif os.path.exists(COOKIE_FILE_TXT):
        print(f"Loading cookies from TXT: {COOKIE_FILE_TXT}")
        with open(COOKIE_FILE_TXT, 'r', encoding='utf-8') as f:
            cookie_content = f.read()
        cookies = parse_cookies_txt(cookie_content)
    else:
        print(f"Error: No cookie files found.")
        print(f"Checked: {COOKIE_FILE_JSON}")
        print(f"Checked: {COOKIE_FILE_TXT}")
        return

    if not cookies:
        print("Error: No cookies parsed.")
        return

    # 2. 准备 Session
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    # 3. 初始化或恢复进度
    current_page = START_PAGE
    file_mode = 'w'
    
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as cf:
                content = cf.read().strip()
                if content.isdigit():
                    saved_page = int(content)
                    if saved_page > 1:
                        print(f"Found checkpoint. Resuming from page {saved_page}...")
                        current_page = saved_page
                        file_mode = 'a' # 追加模式
        except Exception as e:
            print(f"Error reading checkpoint: {e}. Starting from beginning.")

    # 确保输出目录存在
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # 打开 CSV 文件
    with open(OUTPUT_FILE, file_mode, encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "topic_title", "content", "url"])
        
        # 如果是新文件（覆盖模式），写入表头
        if file_mode == 'w':
            writer.writeheader()

        total_items = 0
        page = current_page

        # 4. 循环抓取
        print(f"Starting scrape for User UID: {TARGET_UID} from Page {page}")
        
        while page <= MAX_PAGE:
            # 构造搜索该用户发帖的 URL (searchpost=1 代表搜索回复)
            url = f"https://nga.178.com/thread.php?authorid={TARGET_UID}&searchpost=1&page={page}"
            print(f"Scraping Page {page}: {url}")

            response = None
            retry_count = 0
            success = False

            while retry_count < MAX_RETRIES:
                try:
                    response = session.get(url, timeout=20)
                    response.encoding = 'gbk' # NGA 通常是 GBK 编码
                    
                    # 检查内容是否包含“系统繁忙”等关键词
                    if "系统繁忙" in response.text or "频率过快" in response.text:
                        print(f"Warning: Rate limit or system busy detected (Attempt {retry_count+1}/{MAX_RETRIES}). Waiting {RETRY_WAIT_BASE}s...")
                        time.sleep(RETRY_WAIT_BASE + random.uniform(5, 15))
                        retry_count += 1
                        continue
                    
                    if "访客不能" in response.text: # Cookie 失效
                         print("FATAL: Cookie seems expired (Guest access). Stopping retries.")
                         break

                    success = True
                    break # 请求成功，跳出重试循环

                except Exception as e:
                    print(f"Request failed: {e}. Retrying ({retry_count+1}/{MAX_RETRIES})...")
                    time.sleep(10 * (retry_count + 1))
                    retry_count += 1
            
            if not success:
                print(f"Error: Failed to fetch page {page} after {MAX_RETRIES} attempts. Skipping or Stopping.")
                break # 或者 continue，视情况而定，这里直接break比较稳妥

            if "访客不能" in response.text:
                print("FATAL: Cookies invalid or expired. Access denied (Guest mode detected).")
                break

            soup = BeautifulSoup(response.text, 'html.parser')

            # === 解析逻辑修改 ===
            # NGA 搜索结果页通常是一个 id="topic_rows" 的 table (实际上现在是 topicrows)
            topic_table = soup.find('table', id='topicrows')

            if not topic_table:
                # 尝试旧 ID 兼容
                topic_table = soup.find('table', id='topic_rows')

            if not topic_table:
                # 如果没有找到列表，可能是由于权限、无数据或页面结构变化
                if "没有符合条件的结果" in response.text:
                    print("No more results found.")
                    break
                
                print(f"Warning: Could not find topic table on page {page}.")
                print(f" Dumping HTML to {DEBUG_HTML_FILE} for inspection.")
                with open(DEBUG_HTML_FILE, "w", encoding="utf-8") as debug_f:
                    debug_f.write(response.text)
                
                # Check for common error messages in the dumped text
                if "访客不能" in response.text:
                     print(" -> Reason: Looks like you are not logged in.")
                elif "系统繁忙" in response.text:
                     print(" -> Reason: System busy or rate limited.")
                
                break

            # 获取所有行 (tbody 下的 tr)
            rows = topic_table.find_all('tr')
            found_on_page = 0

            for row in rows:
                try:
                    # 跳过表头
                    if 'class' in row.attrs and 'head' in row.attrs['class']:
                        continue

                    # 查找内容单元格 (通常是 class="c2" 或包含 subject 的 td)
                    subject_td = row.find('td', class_='c2')
                    if not subject_td:
                        continue

                    # 1. 提取帖子链接和标题
                    title_link = subject_td.find('a', class_='topic')
                    if not title_link:
                        continue

                    topic_title = title_link.get_text(strip=True)
                    
                    # 尝试提取 PID 和 TID 从链接
                    # 链接示例: /read.php?tid=45974302&pid=856840078
                    href = title_link.get('href')
                    pid_match = re.search(r'pid=(\d+)', href)
                    tid_match = re.search(r'tid=(\d+)', href)
                    
                    pid = pid_match.group(1) if pid_match else None
                    
                    # 如果没有 PID，可能是直接回复主题，尝试从 commonui.postDispMini 脚本参数中提取
                    if not pid:
                        # 查找 script
                         for script in subject_td.find_all('script'):
                             if script.string and 'commonui.postDispMini' in script.string:
                                 # (..., 45974302,856840078, ...)
                                 # extract integers
                                 nums = re.findall(r'\b(\d+)\b', script.string)
                                 # 典型的参数顺序中，PID 通常是较大的那个数，或者在 TID 之后
                                 # 45974302 (8位) vs 856840078 (9位)
                                 # 简单策略：找最大的那个数字可能是 PID (如果 > 100000000)
                                 for n in nums:
                                     if len(n) >= 9:
                                         pid = n
                                         break
                    
                    final_date = "Unknown"
                    final_content = "Fetch Failed"
                    final_url = f"https://nga.178.com{href}" if href.startswith('/') else href
                    
                    if pid:
                        # 2. 深度抓取：获取准确时间和完整内容
                        # 增加一点随机延迟，防止请求过于密集
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        detail_url = f"https://nga.178.com/read.php?pid={pid}"
                        print(f"    -> Fetching detail for PID {pid}...")
                        
                        try:
                            d_resp = session.get(detail_url, timeout=15)
                            d_resp.encoding = 'gbk'
                            
                            if "访客不能" not in d_resp.text:
                                d_soup = BeautifulSoup(d_resp.text, 'html.parser')
                                
                                # 寻找锚点来确定该 PID 在当前页面的索引 (postrow index)
                                # <a id='pid856840078Anchor'></a>
                                anchor = d_soup.find('a', id=f'pid{pid}Anchor')
                                
                                if anchor:
                                    # 向上找到容器 td class='c2' id='postcontainerX'
                                    container_td = anchor.find_parent('td', class_='c2')
                                    if container_td:
                                        container_id = container_td.get('id', '')
                                        # id="postcontainer0" -> index=0
                                        idx_match = re.search(r'postcontainer(\d+)', container_id)
                                        if idx_match:
                                            idx = idx_match.group(1)
                                            
                                            # get content: id='postcontent0'
                                            content_p = d_soup.find(id=f'postcontent{idx}')
                                            if content_p:
                                                #处理引用，保留上下文
                                                # 尝试找到引用块
                                                # NGA 引用通常是 text: [quote]...[/quote] 或者 div class='quote' (如果被解析)
                                                # 既然上面的 debug HTML 显示是 [quote]...[/quote] 在 p 标签里，我们需要手动解析 text
                                                
                                                full_text = content_p.get_text(separator='\n', strip=True)
                                                
                                                # 简单的正则提取引用
                                                # 匹配标准 NGA 引用头: [b]Post by [uid=...] User (Time):[/b]
                                                # 注意：BeautifulSoup get_text 可能会把 [quote] 这种标签保留为文本，也可能去掉了
                                                # 我们看 debug HTML: <p ...>[quote]...[/quote]...</p>
                                                # 这意味着 [quote] 是作为文本存在的
                                                
                                                # 提取引用对象
                                                reply_target = "Unknown"
                                                quote_content = ""
                                                main_content = full_text
                                                
                                                # 尝试匹配引用头
                                                # 例子: Post by [uid=67086272]冷酷鸡腿堡game[/uid]
                                                # get_text() 之后可能会变成: Post by [uid=67086272]冷酷鸡腿堡game[/uid]
                                                
                                                quote_match = re.search(r'Post by \[uid=\d+\](.*?)\[/uid\]', full_text)
                                                if quote_match:
                                                    reply_target = quote_match.group(1)
                                                
                                                # 尝试分离引用内容和回复内容
                                                # 如果文本以 [quote] 开头，以 [/quote] 结束引用的部分
                                                if '[quote]' in full_text and '[/quote]' in full_text:
                                                    parts = full_text.split('[/quote]', 1)
                                                    if len(parts) > 1:
                                                        quote_part = parts[0].replace('[quote]', '').strip()
                                                        main_content = parts[1].strip()
                                                        
                                                        # 清理引用部分的杂项 (如 pid link, Post by line)
                                                        # 简单保留 quote_part 原样作为 "引用内容"
                                                        quote_content = quote_part
                                                        
                                                        final_content = f"回复 [{reply_target}]: {main_content}\n\n--- 引用内容 ---\n{quote_content}"
                                                    else:
                                                         final_content = full_text # 没分离开
                                                else:
                                                    # 可能是 div class='quote' 已经被解析的情况?
                                                    # 检查是否有 div class='quote'
                                                    quote_div = content_p.find('div', class_='quote')
                                                    if quote_div:
                                                        quote_text = quote_div.get_text(separator=' ', strip=True)
                                                        main_text = content_p.get_text(separator=' ', strip=True).replace(quote_text, '').strip()
                                                        final_content = f"回复 [某人]: {main_text}\n\n--- 引用 ---\n{quote_text}"
                                                    else:
                                                        final_content = full_text

                                            
                                            # get date: id='postdate0'
                                            date_span = d_soup.find(id=f'postdate{idx}')
                                            if date_span:
                                                final_date = date_span.get_text(strip=True)
                                            else:
                                                pass
                        except Exception as e_detail:
                            print(f"    -> Detail fetch failed: {e_detail}")
                    else:
                        print(f"    -> Warning: Could not find PID for row. Using search result data.")
                        # ... fallback logic (extract text from search row as best effort) ...
                        # (Reuse previous logic for fallback)
                        content_text = subject_td.get_text(separator=' ', strip=True)
                        content_text = content_text.replace(topic_title, '').strip()
                        final_content = content_text[:200] # marker for incomplete

                    # 写入数据
                    row_data = {
                        "date": final_date,
                        "topic_title": topic_title,
                        "content": final_content,
                        "url": final_url
                    }
                    writer.writerow(row_data)
                    found_on_page += 1
                    total_items += 1

                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            f.flush()
            print(f"  -> Found {found_on_page} items.")

            # 保存检查点 (保存下一页页码)
            try:
                with open(CHECKPOINT_FILE, 'w') as cf:
                    cf.write(str(page + 1))
                print(f"  -> Page {page} data flushed and checkpoint saved (Next: {page + 1}).")
            except Exception as e:
                print(f"Warning: Failed to save checkpoint: {e}")

            # 检查是否有下一页
            # NGA 的下一页按钮通常是 title="下一页" 或包含文字 ">" / "下一页" 的链接
            next_page_btn = soup.find('a', title='下一页')
            
            if not next_page_btn:
                # 尝试通过文本内容找
                for a_tag in soup.find_all('a'):
                     if a_tag.get_text(strip=True) == '>' or "下一页" in a_tag.get_text(strip=True):
                         # check if it is a link
                         if 'href' in a_tag.attrs:
                             next_page_btn = a_tag
                             break
            
            if not next_page_btn:
                print("No next page button found. Finished.")
                break

            page += 1
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    print(f"Done. Total extracted: {total_items}")


if __name__ == "__main__":
    scrape_user_replies()