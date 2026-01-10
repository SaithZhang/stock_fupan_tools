import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import time
import random

# Configuration
THREAD_ID = "44198753"
BASE_URL = f"https://nga.178.com/read.php?tid={THREAD_ID}"
TARGET_UID = "66662897"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "input", "nga_cookies.txt")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "output", "nga_reviews.csv")

def parse_cookies(cookie_content):
    """Parse cookie string into a dictionary."""
    cookies = {}
    lines = cookie_content.splitlines()
    valid_lines = []
    for line in lines:
        if "Please paste" in line or "Format:" in line:
            continue
        if line.strip():
            valid_lines.append(line.strip())
            
    raw_cookie = "".join(valid_lines)
    print(f"DEBUG: Read cookie string length: {len(raw_cookie)}")
    if len(raw_cookie) < 50:
         print(f"DEBUG: Cookie string too short? content: {raw_cookie}")

    for item in raw_cookie.split(';'):
        if '=' in item:
            name, value = item.split('=', 1)
            cookies[name.strip()] = value.strip()
    return cookies

def scrape_nga_reviews():
    # Load Cookies
    if not os.path.exists(COOKIE_FILE):
        print(f"Error: Cookie file not found at {COOKIE_FILE}")
        return

    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookie_content = f.read()
    
    cookies = parse_cookies(cookie_content)
    if not cookies:
        print("Error: No cookies found in file.")
        return
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    # Run loop
    page = 1
    max_page = 100 
    
    print(f"Starting scrape for thread {THREAD_ID} using provided cookies...")
    
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)
    
    total_reviews = 0
    
    # Open CSV for incremental writing
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["date", "content", "url"])
        writer.writeheader()
        
        try:
            while page <= max_page:
                print(f"Scraping page {page}...")
                url = f"{BASE_URL}&page={page}"
                
                try:
                    response = session.get(url, timeout=15)
                    response.encoding = 'gbk' 
                except Exception as e:
                    print(f"Request error: {e}")
                    time.sleep(5)
                    continue
                
                if response.status_code != 200:
                    print(f"Error: Status code {response.status_code}")
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check login
                if "访客不能" in soup.text:
                    print("FATAL: Cookies invalid or expired. Access denied.")
                    break
                    
                # Find posts
                # Correct selector: table.postbox
                post_tables = soup.find_all('table', class_='postbox')
                
                if not post_tables:
                    # Fallback to post_table just in case
                    post_tables = soup.find_all('table', class_='post_table')
                
                if not post_tables:
                    print(f"No posts found on page {page}. Content len: {len(response.text)}")
                    if "楼主" not in response.text and page > 1:
                        # Double check logical end
                        pass
                
                found_on_page = 0
                for table in post_tables:
                    try:
                        # Author check
                        is_target = False
                        user_link = table.find('a', href=re.compile(r'uid=' + TARGET_UID))
                        if user_link:
                            is_target = True
                        else:
                            user_info = table.find(class_='posterinfo') or table.find(class_='author')
                            if user_info and TARGET_UID in str(user_info):
                                is_target = True
                        
                        if not is_target:
                            continue
                        
                        # Content
                        content_span = table.find('span', id=re.compile(r'postcontent'))
                        if not content_span:
                            content_span = table.find(class_='postcontent')
                        
                        if not content_span:
                            continue
                            
                        content_text = content_span.get_text(strip=True)
                        
                        # Review Filter: Relaxed
                        # Include if "复盘" exists OR length > 50 (likely a detailed post)
                        matches_keyword = "复盘" in content_text or "总结" in content_text or "板块" in content_text
                        is_long_enough = len(content_text) > 50
                        
                        if not (matches_keyword or is_long_enough):
                            continue
                            
                        # Date extraction
                        full_text = table.get_text()
                        date_match = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", full_text)
                        post_date = date_match.group(0) if date_match else "Unknown Date"
                        
                        row = {
                            "date": post_date,
                            "content": content_text,
                            "url": url
                        }
                        writer.writerow(row)
                        f.flush()
                        
                        found_on_page += 1
                        total_reviews += 1
                        preview = content_text[:30].replace('\n', ' ')
                        print(f"  -> Found review ({post_date}): {preview}...")
                        
                    except Exception as e:
                        print(f"Error parsing post: {e}")
                        continue
                
                print(f"  Found {found_on_page} reviews on page {page}")
                
                # Check for next page
                # selector structure: <a title="下一页">
                next_page = soup.find('a', title='下一页') or soup.find('a', string=re.compile('>')) or soup.find('a', class_='next_page')
                
                if not next_page and page > 1:
                    print("No next page found. Stopping.")
                    # Debug: print what we found for pagination
                    pager = soup.find(id='pagebtop')
                    if pager:
                         print(f"Debug Pager: {pager.get_text()[:50]}")
                    break
                    
                page += 1
                time.sleep(random.uniform(1.0, 2.0))
                
        except KeyboardInterrupt:
            print("Interrupted by user.")
        except Exception as e:
            print(f"General error: {e}")
            
    print(f"Finished. Total reviews: {total_reviews}")

if __name__ == "__main__":
    scrape_nga_reviews()
