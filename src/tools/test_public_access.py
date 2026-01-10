from playwright.sync_api import sync_playwright

def test_public():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # F-Lao thread URL
        url = "https://nga.178.com/read.php?tid=44198753"
        print(f"Checking {url}...")
        page.goto(url)
        content = page.content()
        
        if "f佬" in content or "66662897" in content:
            print("SUCCESS: Found content without login!")
            # Check if we can see post content
            posts = page.query_selector_all(".postcontent")
            print(f"Found {len(posts)} posts.")
        else:
            print("FAILURE: Could not find key content. Login might be required.")
            # Print page title or error
            print(f"Page Title: {page.title()}")
            
        browser.close()

if __name__ == "__main__":
    test_public()
