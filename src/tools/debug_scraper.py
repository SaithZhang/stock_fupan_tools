import requests
import os

THREAD_ID = "44198753"
BASE_URL = f"https://nga.178.com/read.php?tid={THREAD_ID}"
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

def debug_dump():
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookie_content = f.read()
    cookies = parse_cookies(cookie_content)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)
    
    url = f"{BASE_URL}&page=1"
    print(f"Fetching {url}...")
    resp = session.get(url)
    resp.encoding = 'gbk'
    
    print(f"Status: {resp.status_code}")
    print(f"Length: {len(resp.text)}")
    
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("Saved to debug_page.html")

if __name__ == "__main__":
    debug_dump()
