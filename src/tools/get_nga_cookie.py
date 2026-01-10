import os
import time
import json
from playwright.sync_api import sync_playwright

# Configuration
THREAD_URL = "https://nga.178.com/read.php?tid=44198753"
# Use a persistent user data directory in the project root to save cookies/session
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "user_data")
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "output", "nga_cookies.json")

def ensure_output_dir():
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)

def get_cookies():
    ensure_output_dir()
    
    print(f"Launching browser...")
    print(f"User Data Dir: {USER_DATA_DIR}")
    
    with sync_playwright() as p:
        # Launch persistent context
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, 
            viewport={"width": 1280, "height": 720},
            # Add args to specific no-sandbox might help stability slightly?
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        
        print("Navigating to NGA...")
        page.goto(THREAD_URL)
        
        print("\n" + "="*50)
        print("WAITING FOR LOGIN...")
        print("Please log in to your account in the opened window.")
        print("The script will automatically detect when you are logged in (looking for UID in page).")
        print("="*50 + "\n")
        
        # Poll for login
        logged_in = False
        wait_seconds = 0
        timeout = 300 # 5 minutes
        
        while wait_seconds < timeout:
            try:
                # Check for indicators of being logged in.
                # E.g., "message" link, or specific user elements.
                # Simple check: search for "用户中心" (User Center) or the specific UID 66662897 is visible? 
                # No, we want to see if *we* are logged in.
                # Usually there is a logout link or username.
                
                content = page.content()
                # "退出" = Logout, "我的" = Mine
                if "u.php" in content or "searchpost" in content or "退出" in content:
                     # Check cookies
                     cookies = page.context.cookies()
                     # Look for specific ngaPassportUid or similar?
                     nga_uid = next((c for c in cookies if 'ngaPassportUid' in c['name']), None)
                     
                     if nga_uid:
                         print(f"Detected Login! UID: {nga_uid['value']}")
                         logged_in = True
                         break
            except Exception as e:
                print(f"Check failed: {e}")
            
            time.sleep(2)
            wait_seconds += 2
            if wait_seconds % 10 == 0:
                print(f"Waiting for login... ({wait_seconds}s)")
                
        if logged_in:
            cookies = page.context.cookies()
            with open(COOKIE_FILE, 'w') as f:
                json.dump(cookies, f, indent=2)
            print(f"SUCCESS: Cookies saved to {COOKIE_FILE}")
            print("Browser will accept close now.")
            time.sleep(2)
        else:
            print("Timed out waiting for login.")
            
        browser.close()

if __name__ == "__main__":
    get_cookies()
