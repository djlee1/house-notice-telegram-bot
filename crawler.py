import os
import json
import hashlib
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

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
    return webdriver.Chrome(options=options)

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def hash_notice(title, link):
    return hashlib.sha256(f"{title}{link}".encode()).hexdigest()

def notify_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def crawl_elyes(url):
    driver = get_driver()
    driver.get(url)
    time.sleep(3)
    rows = driver.find_elements("css selector", ".board-table tbody tr")
    results = []
    for row in rows:
        try:
            title = row.find_element("css selector", "td.subject").text.strip()
            link = row.find_element("css selector", "a").get_attribute("href")
            results.append((title, link))
        except Exception:
            continue
    driver.quit()
    return results

def dispatch_crawler(site):
    if site["type"] == "elyes":
        return crawl_elyes(site["url"])
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

        for title, link in listings:
            h = hash_notice(title, link)
            if h not in site_hashes:
                new_items.append((title, link))
                site_hashes.add(h)

        if new_items:
            for title, link in new_items:
                msg = f"🆕 *{site_name}*\n{title}\n👉 {link}"
                print(msg)
                notify_telegram(msg)

        all_hashes[site_name] = list(site_hashes)

    save_json(HASHES_FILE, all_hashes)

if __name__ == "__main__":
    main()
