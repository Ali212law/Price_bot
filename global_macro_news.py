#!/usr/bin/env python3
# global_macro_news.py — Macro News Logger (READ-ONLY for M9)
# این اسکریپت فقط اخبار را لاگ می‌کند و هیچ تأثیری روی تریدهای M9 ندارد.

import os, json, base64, requests, re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
LOG_FILE = "macro_news_log.json"
MAX_RECORDS = 500

# منابع خبری معتبر کریپتو و اقتصاد کلان
NEWS_FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "cryptoslate": "https://cryptoslate.com/feed/",
}

# کلمات کلیدی که نشان‌دهنده «مکانیزم مولد» هستند (پنهان از چشم تکنیکال)
MACRO_KEYWORDS = {
    "war": ["war", "invasion", "military", "attack", "conflict", "strike"],
    "fed": ["fed", "federal reserve", "interest rate", "fomc", "powell", "inflation", "cpi"],
    "hack": ["hack", "exploit", "stolen", "breach", "vulnerability"],
    "regulation": ["sec", "lawsuit", "ban", "regulation", "crackdown", "sue"],
    "liquidation": ["liquidation", "bankrupt", "insolvency", "collapse", "margin call"],
    "whale": ["whale", "dump", "selloff", "sell-off"],
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return [], None
    except: return [], None

def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_feed(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200: return []
        try:
            root = ET.fromstring(r.content)
            titles = [re.sub(r"<[^>]+>", "", item.find("title").text).strip() 
                     for item in root.findall(".//item")[:15] 
                     if item.find("title") is not None and item.find("title").text]
            return titles
        except:
            titles = re.findall(r"<title>(.*?)</title>", r.text, re.DOTALL)
            return [re.sub(r"<[^>]+>", "", t).strip() for t in titles if len(t.strip()) > 15][:15]
    except: return []

def classify_news(title):
    """تشخیص اینکه خبر مربوط به کدام مکانیزم مولد است"""
    tl = title.lower()
    events = []
    for category, keywords in MACRO_KEYWORDS.items():
        for kw in keywords:
            if kw in tl:
                events.append(category)
                break
    return events

def main():
    now = datetime.now(timezone.utc).isoformat()
    print(f"=== Fetching Macro News ({now}) ===")
    
    all_headlines = []
    for name, url in NEWS_FEEDS.items():
        headlines = fetch_feed(url)
        print(f"  {name}: {len(headlines)} headlines")
        for h in headlines:
            events = classify_news(h)
            if events: # فقط اخبار مهم (با مکانیزم مولد) را ذخیره کن
                all_headlines.append({
                    "time": now,
                    "source": name,
                    "title": h[:200],
                    "events": events
                })

    if not all_headlines:
        print("No macro events detected in this cycle.")
        return

    log, sha = load_from_github(LOG_FILE)
    if not isinstance(log, list): log = []
    
    # جلوگیری از تکرار
    existing_titles = {entry["title"] for entry in log}
    new_entries = [e for e in all_headlines if e["title"] not in existing_titles]
    
    print(f"New macro events detected: {len(new_entries)}")
    for e in new_entries:
        print(f"  [{', '.join(e['events'])}] {e['title'][:80]}")
    
    log.extend(new_entries)
    if len(log) > MAX_RECORDS:
        log = log[-MAX_RECORDS:]

    if save_to_github(LOG_FILE, log, sha):
        print(f"Macro log updated. Total records: {len(log)}")

if __name__ == "__main__":
    main()
