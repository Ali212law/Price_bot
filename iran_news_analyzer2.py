import requests
import json
import re
import hashlib
import os
import base64
import time
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
CHAT_ID = os.environ.get("BALE_CHAT_ID", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = "Ali212law/Price_bot"

IRAN_NEWS_FILE = "iran_news_data.json"

# ═══ منابع کاری ═══
IRAN_FEEDS = {
    "tejaratnews": "https://tejaratnews.com/feed",
    "donya-eqtesad": "https://donya-e-eqtesad.com/feed",
    "mehr_economy": "https://www.mehrnews.com/rss/tp/104",
    "khabaronline": "https://www.khabaronline.ir/rss",
    "irna": "https://www.irna.ir/rss",
    "hamshahri": "https://www.hamshahrionline.ir/rss",
}

# ═══ الگوهای رویداد ═══
EVENT_PATTERNS = {
    "fx": {
        "name_fa": "ارز",
        "keywords": ["دلار", "ارز", "نرخ ارز", "تتر", "یورو",
                     "بازار ارز", "قیمت دلار", "نرخ دلار", "صرافی",
                     "USDT", "ارز دیجیتال", "رمزارز"],
        "exclude": ["دلار کانادا", "دلار استرالیا", "دلار سنگاپور"],
        "direction": "up",
        "btc_impact": "up",
    },
    "inflation": {
        "name_fa": "تورم",
        "keywords": ["تورم", "نرخ تورم", "گرانی", "افزایش قیمت‌ها"],
        "exclude": ["تورم توکیو", "تورم ژاپن", "تورم آمریکا",
                    "تورم اروپا", "تورم چین", "تورم آلمان"],
        "direction": "up",
        "btc_impact": "up",
    },
    "sanctions": {
        "name_fa": "تحریم",
        "keywords": ["تحریم", "تحریم‌های", "فشار حداکثری"],
        "exclude": ["تحریم ورزشی", "تحریم فوتبال", "تحریم باشگاه"],
        "direction": "negative",
        "btc_impact": "up",
    },
    "agreement": {
        "name_fa": "توافق/مذاکره",
        "keywords": ["توافق", "برجام", "مذاکره", "توافق هسته‌ای",
                     "لغو تحریم", "رفع تحریم"],
        "exclude": ["توافق ورزشی", "توافق باشگاهی"],
        "direction": "positive",
        "btc_impact": "down",
    },
    "central_bank": {
        "name_fa": "بانک مرکزی",
        "keywords": ["بانک مرکزی", "نقدینگی", "سیاست پولی",
                     "نرخ بهره", "بازار پول"],
        "exclude": [],
        "direction": "unclear",
        "btc_impact": "unclear",
    },
    "gold": {
        "name_fa": "طلا",
        "keywords": ["قیمت طلا", "سکه", "بازار طلا", "طلا امروز",
                     "طلای آب‌شده", "سکه امامی"],
        "exclude": ["مدال طلا", "ساغر مرادی", "تکواندو", "طلا در ورزش",
                    "ورزشی"],
        "direction": "up",
        "btc_impact": "unclear",
    },
    "oil": {
        "name_fa": "نفت",
        "keywords": ["قیمت نفت", "صادرات نفت", "پتروشیمی", "بنزین",
                     "اوپک", "شانا", "نفت خام", "میعانات"],
        "exclude": ["نفت خوراکی", "نفت ورزشی"],
        "direction": "up",
        "btc_impact": "unclear",
    },
    "stock": {
        "name_fa": "بورس",
        "keywords": ["بورس", "شاخص بورس", "بازار سرمایه",
                     "شاخص کل", "بورس تهران"],
        "exclude": ["بورس ورزشی", "بورس کالا"],
        "direction": "up",
        "btc_impact": "unclear",
    },
    "energy": {
        "name_fa": "انرژی",
        "keywords": ["قطعی برق", "کمبود گاز", "بحران انرژی",
                     "بحران برق", "خاموشی"],
        "exclude": ["برق ورزشگاه"],
        "direction": "negative",
        "btc_impact": "down",
    },
    "crypto": {
        "name_fa": "رمزارز",
        "keywords": ["کریپتو", "ارز دیجیتال", "بیت‌کوین", "رمزارز",
                     "رمز ارز", "بیت کوین", "اتریوم"],
        "exclude": [],
        "direction": "neutral",
        "btc_impact": "unclear",
    },
    "budget": {
        "name_fa": "بودجه/مالیات",
        "keywords": ["بودجه", "مالیات", "لایحه بودجه", "مالیاتی"],
        "exclude": [],
        "direction": "unclear",
        "btc_impact": "unclear",
    },
    "trade": {
        "name_fa": "تجارت",
        "keywords": ["صادرات", "واردات", "تجارت", "تراز تجاری",
                     "گمرک"],
        "exclude": [],
        "direction": "unclear",
        "btc_impact": "unclear",
    },
    "subsidy": {
        "name_fa": "یارانه",
        "keywords": ["یارانه", "قیمت بنزین", "قیمت سوخت"],
        "exclude": ["یارانه ورزشی"],
        "direction": "unclear",
        "btc_impact": "unclear",
    },
}

# ═══ فیلتر خارجی ═══
IRAN_MARKERS = [
    "ایران", "تهران", "بانک مرکزی", "ریال", "تومان",
    "بورس تهران", "دلار تهران", "بازار ایران",
    "اقتصاد ایران", "دولت ایران", "مجلس ایران",
]

GLOBAL_BTC_MARKERS = [
    "etf", "بیت‌کوین", "بیت کوین", "btc", "فدرال رزرو",
    "نرخ بهره آمریکا", "پاول", "کریپتو", "رمزارز",
    "اتریوم", "eth", "بلک‌راک", "بایننس",
]

# فقط اینا اگه با هم بیان، خارجی محسوب می‌شن
FOREIGN_MARKERS = [
    "توکیو", "ژاپن", "کره جنوبی", "کره شمالی", "برزیل",
    "زلنسکی", "پوتین", "اوکراین", "آلمان", "فرانسه",
    "ایتالیا", "اسپانیا", "کانادا", "استرالیا",
]


def normalize_persian(text):
    """نرمال‌سازی متن فارسی"""
    if not text:
        return ""
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ").replace("\u200f", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def title_hash(title):
    """هش برای deduplication"""
    normalized = normalize_persian(title).lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]


def request_with_retry(url, headers=None, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in [200, 404]:
                return r
        except Exception as e:
            print(f"  RETRY {attempt+1}: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
        except Exception as e:
            print(f"  PUT RETRY: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = request_with_retry(url, headers=headers)
        if r and r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        return None, None
    except Exception as e:
        print(f"LOAD ERROR: {e}")
        return None, None


def save_to_github(filename, data, sha=None):
    try:
        if not sha:
            _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha:
            payload["sha"] = sha
        r = put_with_retry(url, headers, payload)
        if r and r.status_code in [200, 201]:
            print(f"SAVED: {filename}")
            return True
        return False
    except Exception as e:
        print(f"SAVE ERROR: {e}")
        return False


def send_message(text):
    if not BALE_TOKEN:
        return None
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None


def fetch_feed(name, url):
    print(f"\nFETCHING: {name}")
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        print(f"Status: {r.status_code}")
        if r.status_code != 200:
            return []

        try:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//entry")
            print(f"✅ {len(items)} items")

            titles = []
            for item in items[:50]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pubdate_elem = item.find("pubDate")
                if pubdate_elem is None:
                    pubdate_elem = item.find("published")

                title = title_elem.text if title_elem is not None else ""
                link = link_elem.text if link_elem is not None else ""
                pubdate = pubdate_elem.text if pubdate_elem is not None else ""

                title = re.sub(r"<[^>]+>", "", title).strip()
                if title and len(title) > 15:
                    titles.append({
                        "title": title,
                        "link": link,
                        "published": pubdate,
                        "source": name,
                    })
            return titles
        except ET.ParseError as e:
            print(f"⚠️ XML Error: {e}")
            return []
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return []


def detect_events(title):
    """تشخیص رویدادها"""
    found = []

    for event_key, config in EVENT_PATTERNS.items():
        excluded = False
        for ex in config.get("exclude", []):
            if ex in title:
                excluded = True
                break
        if excluded:
            continue

        for kw in config["keywords"]:
            if kw in title:
                found.append({
                    "event": event_key,
                    "name_fa": config["name_fa"],
                    "matched_kw": kw,
                    "direction": config["direction"],
                    "btc_impact": config["btc_impact"],
                })
                break

    return found


def classify_relevance(title):
    """
    بهبودیافته: پیش‌فرض iran برای منابع اقتصادی
    """
    title_lower = title.lower()

    # ۱) اگه صریحاً ایران یا اقتصاد ایران → iran
    if any(kw in title for kw in IRAN_MARKERS):
        return "iran"

    # ۲) global BTC check
    if any(kw in title_lower for kw in GLOBAL_BTC_MARKERS):
        return "global_btc"

    # ۳) چک کن اگه خارجیه
    for f in FOREIGN_MARKERS:
        if f in title:
            # ولی اگه کلمه‌ی ایران یا BTC هم داشت → رد نکن
            if not any(kw in title for kw in IRAN_MARKERS):
                if not any(kw in title_lower for kw in GLOBAL_BTC_MARKERS):
                    return "foreign_irrelevant"

    # ۴) پیش‌فرض: iran (چون منابع ما اقتصادی ایرانن)
    return "iran"


def parse_published(published_str):
    if not published_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(published_str.strip(), fmt).isoformat()
        except:
            continue
    return published_str


def main():
    print("=" * 60)
    print("  IRAN NEWS ANALYZER v2")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")

    now = datetime.now()
    all_items = []

    for name, url in IRAN_FEEDS.items():
        items = fetch_feed(name, url)
        all_items.extend(items)

    print(f"\n📊 Total raw: {len(all_items)}")

    # Dedup
    seen_hashes = set()
    unique_items = []
    duplicates_count = 0

    for item in all_items:
        h = title_hash(item["title"])
        if h in seen_hashes:
            duplicates_count += 1
            continue
        seen_hashes.add(h)
        item["hash"] = h
        item["normalized_title"] = normalize_persian(item["title"])
        item["fetched_at"] = now.isoformat()
        item["published_at"] = parse_published(item.get("published", ""))
        item["is_duplicate"] = False
        unique_items.append(item)

    print(f"📊 Unique: {len(unique_items)} | Duplicates: {duplicates_count}")

    # تحلیل
    for item in unique_items:
        title = item["title"]
        item["relevance"] = classify_relevance(title)

        events = detect_events(title)
        item["events"] = events

        if not events:
            item["primary_event"] = None
            item["event_direction"] = "unclear"
            item["btc_impact"] = "unclear"
            item["confidence"] = "low"
        else:
            primary = events[0]
            item["primary_event"] = primary["event"]
            item["primary_event_fa"] = primary["name_fa"]
            item["event_direction"] = primary["direction"]
            item["btc_impact"] = primary["btc_impact"]

            # Confidence
            if item["relevance"] == "iran" and len(events) >= 1:
                item["confidence"] = "medium"
            if len(events) >= 2:
                item["confidence"] = "high"

    # آمار
    stats = {
        "total_raw": len(all_items),
        "total_unique": len(unique_items),
        "duplicates_removed": duplicates_count,
        "by_relevance": {},
        "by_event": {},
        "by_btc_impact": {},
        "by_direction": {},
    }

    for item in unique_items:
        rel = item["relevance"]
        stats["by_relevance"][rel] = stats["by_relevance"].get(rel, 0) + 1

        ev = item["primary_event"]
        if ev:
            stats["by_event"][ev] = stats["by_event"].get(ev, 0) + 1

        imp = item["btc_impact"]
        stats["by_btc_impact"][imp] = stats["by_btc_impact"].get(imp, 0) + 1

        dr = item["event_direction"]
        stats["by_direction"][dr] = stats["by_direction"].get(dr, 0) + 1

    print("\n" + "=" * 60)
    print("  STATS")
    print("=" * 60)
    print(f"Total raw: {stats['total_raw']}")
    print(f"Unique: {stats['total_unique']}")
    print(f"Duplicates: {stats['duplicates_removed']}")
    print(f"\nBy relevance:")
    for k, v in stats["by_relevance"].items():
        print(f"  {k}: {v}")
    print(f"\nBy event:")
    for k, v in sorted(stats["by_event"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"\nBy BTC impact:")
    for k, v in stats["by_btc_impact"].items():
        print(f"  {k}: {v}")

    # ذخیره
    output = {
        "last_update": now.isoformat(),
        "stats": stats,
        "items": unique_items,
    }

    data, sha = load_from_github(IRAN_NEWS_FILE)
    if data and isinstance(data, dict):
        old_items = data.get("items", [])
        old_hashes = {it.get("hash") for it in old_items}
        new_items = [it for it in unique_items if it.get("hash") not in old_hashes]
        merged = old_items + new_items
        merged.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)
        merged = merged[:500]
        output["items"] = merged
        output["stats"]["kept_in_history"] = len(merged)
        output["stats"]["new_added"] = len(new_items)
    else:
        output["items"] = unique_items

    save_to_github(IRAN_NEWS_FILE, output, sha)

    # پیام Bale
    if stats["by_event"]:
        event_lines = "\n".join([
            f"  • {EVENT_PATTERNS.get(k, {}).get('name_fa', k)}: {v}"
            for k, v in sorted(stats["by_event"].items(), key=lambda x: -x[1])[:10]
        ])

        msg = (
            f"📰 تحلیل اخبار ایران v2\n\n"
            f"📊 کل: {stats['total_raw']}\n"
            f"✅ یکتا: {stats['total_unique']}\n"
            f"🔁 تکراری: {stats['duplicates_removed']}\n\n"
            f"🇮🇷 ایران‌محور: {stats['by_relevance'].get('iran', 0)}\n"
            f"🌍 جهانی BTC: {stats['by_relevance'].get('global_btc', 0)}\n"
            f"❌ خارجی: {stats['by_relevance'].get('foreign_irrelevant', 0)}\n\n"
            f"📋 رویدادها:\n{event_lines}\n\n"
            f"🎯 اثر بر BTC/IRT:\n"
            f"  ⬆️ صعودی: {stats['by_btc_impact'].get('up', 0)}\n"
            f"  ⬇️ نزولی: {stats['by_btc_impact'].get('down', 0)}\n"
            f"  ❓ نامشخص: {stats['by_btc_impact'].get('unclear', 0)}"
        )
        send_message(msg)

    print("\n✅ DONE")


if __name__ == "__main__":
    main()
