import os
import json
import hashlib
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# Load secrets from GitHub Actions env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 파일 경로
SITES_FILE = "sites.json"
HASHES_FILE = "hashes.json"

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(options=options, service = service)

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def hash_notice(title, link, date=None):
    if date:
        return hashlib.sha256(f"{title}{link}{date}".encode()).hexdigest()
    return hashlib.sha256(f"{title}{link}".encode()).hexdigest()

def escape_markdown(text):
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return re.sub(rf"([{re.escape(escape_chars)}])", r"\\\1", text)

def notify_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "MarkdownV2",
    }
    resp = requests.post(url, data=payload)
    if resp.status_code != 200:
        print(f"❌ Telegram message failed: {resp.text}")
    else:
        print("✅ Telegram message sent.")


def crawl_elyes(url):
    driver = get_driver()
    driver.get(url)
    time.sleep(3)
    rows = driver.find_elements(By.CSS_SELECTOR, ".lotte-table-2 tbody tr")
    
    import pandas as pd
    data = []
    
    for row in rows:
        try:
            # 모든 td 엘리먼트 가져오기
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            row_data = {}
            
            # 제목과 링크 정보 추출
            title_cell = row.find_element(By.CSS_SELECTOR, "td.tleft a")
            title = title_cell.text.strip()
            modal_target = title_cell.get_attribute("data-target")
            link = f"{url}#{modal_target}"
            
            # 기본 정보 저장
            row_data['title'] = title
            row_data['link'] = link
            
            # 모든 셀 데이터 추출 (인덱스를 컬럼명으로 사용)
            for i, cell in enumerate(cells):
                row_data[f'col_{i}'] = cell.text.strip()
                
            data.append(row_data)
        except Exception as e:
            continue
    
    # 데이터프레임 생성
    df = pd.DataFrame(data)
    driver.quit()
    
    # 원래 형식과 호환되도록 title과 link 튜플 리스트 반환
    results = [(row['title'], row['link']) for _, row in df.iterrows()]
    return results

def crawl_podium830(url):
    driver = get_driver()
    driver.get(url)
    time.sleep(3)
    
    results = []
    try:
        # New selector for the table rows
        notice_items = driver.find_elements(By.CSS_SELECTOR, "table.board-list tbody tr")
        
        for item in notice_items:
            try:
                # Get title from the span inside the div with class "ellip"
                title_elem = item.find_element(By.CSS_SELECTOR, "td.board-list__tit div.ellip span")
                title = title_elem.text.strip()
                
                # Get date from the date column
                date_elem = item.find_element(By.CSS_SELECTOR, "td.board-list__txt")
                date = date_elem.text.strip()
                
                # Skip items with empty title or date
                if not title or not date:
                    continue
                
                # Since we don't have direct links in the table, we'll include the date in the hash
                # The actual link would be created when clicking the row, but we don't have that information
                # Use the URL + title as the link for now
                link = f"{url}#{title}"
                
                results.append((title, link, date))
            except Exception as e:
                continue
    except Exception as e:
        print(f"포디움830 크롤링 오류: {e}")
    
    driver.quit()
    return results

def crawl_soco(url):
    driver = get_driver()
    driver.get(url)
    time.sleep(3)

    results = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "#boardList tr")

        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 4:
                    continue

                link_elem = cells[2].find_element(By.TAG_NAME, "a")
                title = link_elem.text.strip()
                href = link_elem.get_attribute("href")
                if href and not href.startswith("http"):
                    base = "https://soco.seoul.go.kr/youth/bbs/BMSR00015/"
                    href = requests.compat.urljoin(base, href)

                date = cells[3].text.strip()

                if title:
                    results.append((title, href, date))
            except Exception:
                continue
    except Exception as e:
        print(f"소코 크롤링 오류: {e}")

    driver.quit()
    return results

def dispatch_crawler(site):
    if site["type"] == "elyes":
        return crawl_elyes(site["url"])
    elif site["type"] == "podium830":
        return crawl_podium830(site["url"])
    elif site["type"] == "soco":
        return crawl_soco(site["url"])
    else:
        print(f"❗ 지원되지 않는 사이트 유형: {site['type']}")
        return []

def main():
    sites = load_json(SITES_FILE, [])
    all_hashes = load_json(HASHES_FILE, {})

    for site in sites:
        site_name = site["name"]
        print(f"🔍 [{site_name}] 공고 확인 중...")
        listings = dispatch_crawler(site)

        if site_name not in all_hashes:
            all_hashes[site_name] = []

        site_hashes = set(all_hashes[site_name])
        new_items = []

        for item in listings:
            # Handle both old format (title, link) and new format (title, link, date)
            if len(item) == 2:
                title, link = item
                date = None
                h = hash_notice(title, link)
            else:
                title, link, date = item
                h = hash_notice(title, link, date)
                
            if h not in site_hashes:
                new_items.append((title, link, date) if date else (title, link))
                site_hashes.add(h)

        if new_items:
            print(f"✅ [{site_name}] {len(new_items)}개의 새 공고 발견!")
            for item in new_items:
                # 새 공고 감지된 후 메시지 만들기 직전
                if len(item) == 2:
                    title, link = item
                    msg = f"🆕 *{escape_markdown(site_name)}*\n{escape_markdown(title)}\n👉 {escape_markdown(link)}"
                else:
                    title, link, date = item
                    msg = (
                        f"🆕 *{escape_markdown(site_name)}*\n"
                        f"{escape_markdown(title)}\n"
                        f"📅 {escape_markdown(date)}\n"
                        f"👉 {escape_markdown(link)}"
                    )
                notify_telegram(msg)
        else:
            print(f"✅ [{site_name}] 새 공고 없음")

        all_hashes[site_name] = list(site_hashes)

    save_json(HASHES_FILE, all_hashes)
    print("✅ 크롤링 완료")

if __name__ == "__main__":
    main()
