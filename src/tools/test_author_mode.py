import requests
from bs4 import BeautifulSoup
import os

THREAD_ID = "44279886"
TARGET_UID = "66662897"
BASE_URL = f"https://nga.178.com/read.php?tid={THREAD_ID}&authorid={TARGET_UID}"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "input", "nga_cookies.txt")

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

def test_author_filter():
    print(f"Testing URL: {BASE_URL}")
    
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookie_content = f.read()
    cookies = parse_cookies(cookie_content)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)
    
    resp = session.get(BASE_URL)
    resp.encoding = 'gbk'
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    if "访客不能" in soup.text:
         print("Login failed/Access denied.")
         return

    posts = soup.find_all('table', class_='postbox')
    if not posts:
        posts = soup.find_all('table', class_='post_table')
        
    print(f"Found {len(posts)} posts on filtered page 1.")
    
    # Check author of first post
    if posts:
        first_post = posts[0]
        user_link = first_post.find('a', href=True)
        print(f"First post raw links: {[a['href'] for a in first_post.find_all('a', href=True) if 'uid' in a['href']]}")
        
    # Check pagination
    pager = soup.find(id='pagebtop')
    if pager:
        print(f"Pagination info: {pager.get_text()[:100]}")
    else:
        print("No pagination found (single page?).")

if __name__ == "__main__":
    test_author_filter()
