import os
import re
import csv
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
THREAD_URL = "https://nga.178.com/read.php?tid=44198753"
TARGET_UID = "66662897"
# Use a persistent user data directory in the project root to save cookies/session
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "user_data")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "output", "nga_reviews.csv")

def ensure_output_dir():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

def scrape_f_lao_reviews():
    ensure_output_dir()
    
    with sync_playwright() as p:
        # Launch persistent context
        print(f"Launching browser with user data dir: {USER_DATA_DIR}")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, # Must be visible for login interactively
            viewport={"width": 1280, "height": 720}
        )
        
        page = browser.new_page()
        # Handle dialogs (alerts, confirms) automatically
        page.on("dialog", lambda dialog: dialog.accept())
        
        page.goto(THREAD_URL)
        
        # Check login status
        print("Checking login status...")
        try:
            # Look for a common element that appears only when logged in (e.g., user panel, reply box)
            # Or just ask the user directly
            pass 
        except:
            pass
            
                
        print("\n" + "="*50)
        print("PLEASE LOGIN IN THE BROWSER WINDOW NOW IF YOU HAVEN'T ALREADY.")
        print("Once you are logged in and can see the thread content clearly,")
        input("PRESS ENTER HERE TO START SCRAPING...")
        print("="*50 + "\n")
        
        # Explicitly save cookies for user reference (as requested)
        cookies = page.context.cookies()
        import json
        cookie_file = os.path.join(os.path.dirname(OUTPUT_FILE), "nga_cookies.json")
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"Cookies saved to {cookie_file}")

        reviews = []
        
        # Determine total pages
        try:
            # Selector for the last page button or calculating from total replies
            # NGA usually has page buttons like: [1] ... [45]
            # We'll valid this dynamically or start loop
            # Let's clean up the URL to base
            base_url = THREAD_URL.split('&')[0]
            
            # Identify max page
            # Usually '.page_nav .select_page' or similar. 
            # A simple strategy is to scrape page 1, check for 'next page' link.
            
            current_page = 1
            max_page = 1000 # Safety limit
            
            # Start from where we left off if file exists? 
            # For now, just scrape all.
            
            while current_page <= max_page:
                print(f"Scraping page {current_page}...")
                try:
                    page.goto(f"{base_url}&page={current_page}", timeout=60000)
                    page.wait_for_selector("table.post_table", timeout=10000)
                except Exception as e:
                    print(f"Error loading page {current_page}: {e}")
                    # Retry once
                    time.sleep(5)
                    try:
                        page.goto(f"{base_url}&page={current_page}", timeout=60000)
                    except:
                        print("Skipping page due to load error.")
                        current_page += 1
                        continue

                # Extract posts
                posts = page.query_selector_all("table.post_table")
                
                found_on_page = 0
                for post in posts:
                    try:
                        # 1. Check Author
                        author_el = post.query_selector(".userlink")
                        if not author_el:
                            continue
                        
                        # Author ID check - checking href or text
                        # NGA userlink href often: nuke.php?func=ucp&uid=66662897
                        href = author_el.get_attribute("href")
                        # Some userlinks might not have href if deleted, but usually they do
                        if not href or TARGET_UID not in href:
                            continue
                        
                        # 2. Extract Content to check for keywords
                        content_el = post.query_selector("span[id^='postcontent']")
                        if not content_el:
                            # Sometimes content is just in the cell if no span id
                            content_el = post.query_selector(".postcontent")
                            
                        if not content_el:
                            continue
                            
                        content_text = content_el.inner_text()
                        
                        # Filter for "复盘" (Review)
                        if "复盘" not in content_text:
                            continue
                            
                        # 3. Extract Date
                        # We can grab the whole text of the postrow and regex the date
                        post_row_text = post.inner_text()
                        date_match = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", post_row_text)
                        post_date = date_match.group(0) if date_match else "Unknown Date"
                        
                        # Clean content
                        clean_content = content_text.strip()
                        
                        reviews.append({
                            "date": post_date,
                            "content": clean_content,
                            "url": page.url
                        })
                        found_on_page += 1
                        print(f"  -> Found review for date: {post_date}")
                        
                    except Exception as e:
                        print(f"  Error parsing post: {e}")
                        continue
                
                print(f"  Found {found_on_page} reviews on page {current_page}")
                
                # Check for next page
                # If there's a next page button active, or we just increment?
                # A robust way is to check if we are on the last page.
                # NGA pagination usually has a 'next' arrow '>' or we can check the 'page' param in URL vs current
                
                # Simple check for now: if no posts found, maybe stop? 
                # No, empty pages are rare. 
                # Let's check if the "next page" button exists.
                # Class for next page link usually contains `next_page` or we search for `>` text in a link
                next_page_exists = page.query_selector("a[title='后一页']") or page.query_selector("a.next_page") or page.query_selector("a:has-text('>')")
                
                # Also check actual current page element to see if we reached the end
                # If we tried to go to page X and URL redirected or stay, handle that?
                # NGA handles page=9999 by going to last page.
                
                # Heuristic: if we are on page 45, and next is not there.
                if not next_page_exists and current_page > 1:
                    # Double check if we are really at the end
                    print("No next page link found. Stopping.")
                    break
                
                current_page += 1
                time.sleep(1) # Be nice
                
        except Exception as e:
            print(f"Scraping error: {e}")
        finally:
            # Save results
            print(f"Saving {len(reviews)} reviews to {OUTPUT_FILE}...")
            with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["date", "content", "url"])
                writer.writeheader()
                writer.writerows(reviews)
                
            browser.close()

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Ensure src is in path if needed for imports, though we are standalone here
    scrape_f_lao_reviews()
