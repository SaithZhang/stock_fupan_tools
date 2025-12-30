import requests
from bs4 import BeautifulSoup
import time
import random
import os

# ================= 配置区 =================
# 替换为你自己的 NGA Cookie (必须是登录后的，否则看不了历史)
USER_COOKIE = '_178i=1; ngacn0comUserInfo=%25C8%25AB%25B2%25D6%25D5%25D0%25B2%25C6%25CE%25DE%25B5%25D0%09%25E5%2585%25A8%25E4%25BB%2593%25E6%258B%259B%25E8%25B4%25A2%25E6%2597%25A0%25E6%2595%258C%0939%0939%09%0910%090%094%090%090%09; ngaPassportUid=67005896; ngaPassportUrlencodedUname=%25C8%25AB%25B2%25D6%25D5%25D0%25B2%25C6%25CE%25DE%25B5%25D0; ngaPassportCid=X9v0ouf33ieh04fgcolmt3hmr6qta4utcjkq42be; ngacn0comUserInfoCheck=27dff1f50375ef865b56b949eef17c62; ngacn0comInfoCheckTime=1764071080; Hm_lvt_2728f3eacf75695538f5b1d1b5594170=1764041796,1764071082; HMACCOUNT=920481476D13589F; lastvisit=1764071559; lastpath=/thread.php?searchpost=1&authorid=12467316; bbsmisccookies=%7B%22pv_count_for_insad%22%3A%7B0%3A-42%2C1%3A1764090086%7D%2C%22insad_views%22%3A%7B0%3A1%2C1%3A1764090086%7D%2C%22uisetting%22%3A%7B0%3A%22a%22%2C1%3A1764071860%7D%7D; Hm_lpvt_2728f3eacf75695538f5b1d1b5594170=1764071561'

# 目标用户 ID
AUTHOR_ID = '12467316'

# 爬取页数范围 (根据链接，他至少有80页，你可以设为 1 到 81)
START_PAGE = 1
END_PAGE = 91

# 保存文件名
OUTPUT_FILE = f'nga_user_{AUTHOR_ID}_history.md'
# =========================================

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': USER_COOKIE,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9'
}


def get_page_content(page):
    url = f"https://nga.178.com/thread.php?authorid={AUTHOR_ID}&searchpost=1&fid=0&page={page}"
    try:
        # NGA 很多页面是 GBK 编码，如果乱码尝试改为 'gbk'
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'gbk'
        return r.text
    except Exception as e:
        print(f"Error fetching page {page}: {e}")
        return None


def parse_and_save(html, page_num, file_handle):
    soup = BeautifulSoup(html, 'html.parser')

    # NGA 搜索结果页的帖子列表通常在 table 或 div 结构中
    # 注意：searchpost=1 返回的是回复列表

    # 找到所有的帖子容器 (具体 class 可能随 NGA 版本变动，通常是 'topic' 或直接在 table rows)
    # 针对 NGA 搜索页，通常主体内容在 <table class="forumbox postbox">

    tables = soup.find_all('table', class_='forumbox')

    if not tables:
        print(f"Page {page_num}: No content found (Need Check Cookie or HTML structure).")
        return

    count = 0
    for table in tables:
        # 提取帖子标题
        title_tag = table.find('a', class_='topic')
        title = title_tag.get_text().strip() if title_tag else "无标题"
        link = "https://nga.178.com" + title_tag['href'] if title_tag else ""

        # 提取回复内容 (NGA搜索页的内容在 p 标签或直接在 td 中)
        # 这是一个简单的提取逻辑，可能需要根据实际页面微调
        content_tag = table.find('td', class_='c2')
        if not content_tag:
            content_tag = table.find('p', class_='content')  # 备用选择器

        content = content_tag.get_text().strip() if content_tag else "内容解析失败"

        # 提取时间
        time_tag = table.find('span', class_='postdate')
        post_time = time_tag.get_text().strip() if time_tag else "未知时间"

        # 写入文件
        file_handle.write(f"## [{post_time}] 帖子：{title}\n")
        file_handle.write(f"**Link:** {link}\n\n")
        file_handle.write(f"> {content}\n\n")
        file_handle.write("-" * 50 + "\n\n")
        count += 1

    print(f"Page {page_num}: Saved {count} posts.")


def main():
    print(f"开始爬取用户 {AUTHOR_ID} 的回复记录...")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# User {AUTHOR_ID} Post History\n\n")

        for page in range(START_PAGE, END_PAGE + 1):
            html = get_page_content(page)
            if html:
                parse_and_save(html, page, f)

            # === 关键：随机延时，防止封IP ===
            sleep_time = random.uniform(2, 5)
            print(f"Sleeping for {sleep_time:.2f}s...")
            time.sleep(sleep_time)

    print("Done! Check the output file.")


if __name__ == "__main__":
    main()