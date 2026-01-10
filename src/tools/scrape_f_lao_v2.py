import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import time
import random
from datetime import datetime

# Configuration
THREAD_ID = "44279886"
TARGET_UID = "66662897"
BASE_URL = f"https://nga.178.com/read.php?tid={THREAD_ID}&authorid={TARGET_UID}"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "input", "nga_cookies.txt")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "output", "f_lao_reviews_v2.csv")

# Date filter
START_DATE_STR = "2025-09-01"
# Convert to simple int for comparison if needed, or string match priority
# Simple string comparison YYYY-MM-DD works 
START_DATE = datetime.strptime(START_DATE_STR, "%Y-%m-%d")

def parse_cookies(cookie_content):
    cookies = {}
    lines = cookie_content.splitlines()
    valid_lines = []
    for line in lines:
        if "Please paste" in line or "Format:" in line:
            continue
        if line.strip():
            valid_lines.append(line.strip())
    raw_cookie = "".join(valid_lines)
    for item in raw_cookie.split(';'):
        if '=' in item:
            name, value = item.split('=', 1)
            cookies[name.strip()] = value.strip()
    return cookies

def scrape_v2():
    if not os.path.exists(COOKIE_FILE):
        print(f"Error: Cookie file not found.")
        return

    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookie_content = f.read()
    
    cookies = parse_cookies(cookie_content)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)
    
    page = 1
    # Max pages for an author-filtered view should be much less than 4000
    # Let's say max 200 pages if he posts a lot.
    max_page = 500 
    
    total_reviews = 0
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "content", "url"])
        writer.writeheader()
        
        try:
            while page <= max_page:
                print(f"Scraping page {page}...")
                url = f"{BASE_URL}&page={page}"
                
                try:
                    resp = session.get(url, timeout=15)
                    resp.encoding = 'gbk'
                except Exception as e:
                    print(f"Error: {e}")
                    time.sleep(5)
                    continue
                
                if "访客不能" in resp.text:
                    print("FATAL: Access denied (cookies expired?).")
                    break
                    
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                posts = soup.find_all('table', class_='postbox')
                if not posts:
                    posts = soup.find_all('table', class_='post_table')
                
                found_on_page = 0
                for table in posts:
                    # Content
                    content_span = table.find('span', id=re.compile(r'postcontent')) or table.find(class_='postcontent')
                    if not content_span:
                         continue
                    
                    content_text = content_span.get_text(strip=True)
                    
                    # Date
                    full_text = table.get_text()
                    date_match = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", full_text)
                    post_date_str = date_match.group(0) if date_match else "1900-01-01 00:00"
                    
                    # Filter Date
                    try:
                        post_dt = datetime.strptime(post_date_str.split()[0], "%Y-%m-%d")
                        if post_dt < START_DATE:
                            # Skip old posts
                            continue
                    except:
                        pass
                        
                    # Filter Keywords (Relaxed)
                    # "复盘" or "总结" or just detailed text?
                    # The user said: "2025-09-01之后他在另一个帖子一直回复复盘"
                    # So we prioritize "复盘".
                    is_review = "复盘" in content_text or "总结" in content_text
                    
                    # Also include anything substantial if it matches the date criteria?
                    # Let's be safe and include all his posts from this filtered view if they look like market talk.
                    # Or just check length.
                    if len(content_text) > 20: 
                        # Save
                        row = {
                            "date": post_date_str,
                            "content": content_text,
                            "url": url
                        }
                        writer.writerow(row)
                        f.flush()
                        found_on_page += 1
                        total_reviews += 1
                        print(f"  -> Found: {post_date_str} {content_text[:20]}...")
                
                print(f"  Found {found_on_page} posts on page {page}")
                
                # Check next page
                next_page = soup.find('a', title='下一页') or soup.find('a', string=re.compile('>')) or soup.find('a', class_='next_page')
                if not next_page and page > 1:
                    print("No next page. Stopping.")
                    break
                    
                page += 1
                time.sleep(random.uniform(1.0, 2.0))

        except KeyboardInterrupt:
            print("Interrupted.")
            
    print(f"Done. Total: {total_reviews}")

if __name__ == "__main__":
    scrape_v2()
