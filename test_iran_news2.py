import requests
import json
import re
from datetime import datetime
from xml.etree import ElementTree as ET

# ═══ منابع RSS ایران (بهبودیافته) ═══
IRAN_FEEDS = {
    "irna": "https://www.irna.ir/rss",
    "tasnim": "https://www.tasnimnews.com/rss",
    "fars": "https://www.farsnews.ir/rss",
    "khabaronline": "https://www.khabaronline.ir/rss",
    "tejaratnews": "https://tejaratnews.com/feed",
    "eghtesadonline": "https://www.eghtesadonline.com/feed",
    "donya-eqtesad": "https://donya-e-eqtesad.com/feed",
    "istna": "https://istna.ir/feed",
    "hamshahri": "https://www.hamshahrionline.ir/rss",
    "mehr_economy": "https://www.mehrnews.com/rss/tp/104",
}

# ═══ کلمات کلیدی با context ═══
# هر کلمه باید توی یه جمله‌ی مربوط باشه (نه فقط توی عنوان)
IRAN_KEYWORDS = {
    "sanctions": {
        "words": ["تحریم", "تحریم‌های", "sanction"],
        "exclude": ["تحریم‌های ورزشی", "تحریم فوتبال"],
    },
    "inflation": {
        "words": ["تورم", "inflation", "نرخ تورم"],
        "exclude": [],
    },
    "dollar": {
        "words": ["دلار", "قیمت دلار", "نرخ دلار", "بازار ارز"],
        "exclude": ["دلار کانادا", "دلار آمریکا در", "قهرمانی", "ورزشی"],
    },
    "agreement": {
        "words": ["توافق", "برجام", "مذاکره", "توافق هسته‌ای"],
        "exclude": ["توافق ورزشی", "توافق باشگاهی"],
    },
    "crisis": {
        "words": ["بحران اقتصادی", "بحران ارزی", "بحران مالی"],
        "exclude": ["بحران باشگاه", "بحران ورزشی"],
    },
    "war": {
        "words": ["جنگ اقتصادی", "حمله نظامی", "تنش نظامی", "جنگ تجاری"],
        "exclude": ["جنگ ورزشی", "جنگ فوتبال", "ترمیم جنگ", "آسیب جنگ"],
    },
    "central_bank": {
        "words": ["بانک مرکزی", "نقدینگی", "سیاست پولی"],
        "exclude": [],
    },
    "oil": {
        "words": ["نفت", "قیمت نفت", "صادرات نفت", "پتروشیمی"],
        "exclude": ["نفت خوراکی", "نفت ورزشی"],
    },
    "gold": {
        "words": ["طلا", "سکه", "قیمت طلا", "بازار طلا"],
        "exclude": ["طلا در ورزش", "مدال طلا", "ساغر مرادی", "تکواندو"],
    },
    "crypto": {
        "words": ["کریپتو", "ارز دیجیتال", "بیت‌کوین", "رمزارز", "رمز ارز"],
        "exclude": [],
    },
    "budget": {
        "words": ["بودجه", "مالیات", "لایحه بودجه"],
        "exclude": [],
    },
    "subsidy": {
        "words": ["یارانه", "قیمت بنزین", "قیمت سوخت"],
        "exclude": ["یارانه ورزشی"],
    },
    "stock": {
        "words": ["بورس", "شاخص بورس", "بازار سرمایه"],
        "exclude": ["بورس ورزشی"],
    },
    "interest_rate": {
        "words": ["نرخ بهره", "سود بانکی", "نرخ سود"],
        "exclude": [],
    },
}

# ═══ کلمات احساسی (بهبودیافته) ═══
POSITIVE_IR = [
    "توافق", "برجام", "کاهش تحریم", "لغو تحریم", "افزایش صادرات",
    "رشد اقتصادی", "کنترل تورم", "صلح", "مذاکره موفق",
    "آزادسازی", "کاهش تنش", "بهبود روابط", "رفع تحریم",
]

NEGATIVE_IR = [
    "افزایش تورم", "کاهش ارزش ریال", "سقوط بورس", "جنگ اقتصادی",
    "تحریم جدید", "فشار حداکثری", "بحران ارزی", "قطعنامه",
    "تشدید تحریم", "خروج آمریکا", "برگشت تحریم‌ها",
]


def fetch_feed(name, url, timeout=15):
    """دریافت یه فید RSS"""
    print(f"\n{'='*60}")
    print(f"FETCHING: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")
        print(f"Size: {len(r.content)} bytes")

        if r.status_code != 200:
            print(f"❌ FAILED")
            return []

        # پارس XML
        try:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//entry")  # Atom feeds

            print(f"✅ Parsed - {len(items)} items")

            titles = []
            for item in items[:15]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pubdate_elem = item.find("pubDate") or item.find("published")

                title = title_elem.text if title_elem is not None else ""
                link = link_elem.text if link_elem is not None else ""
                pubdate = pubdate_elem.text if pubdate_elem is not None else ""

                title = re.sub(r"<[^>]+>", "", title).strip()

                if title and len(title) > 10:
                    titles.append({
                        "title": title,
                        "link": link,
                        "time": pubdate,
                        "source": name,
                    })
                    print(f"  • {title[:85]}")

            return titles

        except ET.ParseError as e:
            print(f"⚠️ XML Parse Error: {e}")
            titles = re.findall(r"<title[^>]*>(.*?)</title>", r.text, re.DOTALL)
            titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles if t.strip()]
            titles = [t for t in titles if len(t) > 15][:15]
            print(f"✅ Regex fallback - {len(titles)}")
            return [{"title": t, "link": "", "time": "", "source": name} for t in titles]

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return []


def match_keyword_context(title, words, exclude_words):
    """
    چک می‌کنه که آیا کلمه‌ای از words توی عنوان هست،
    و کلمه‌ی exclude توی همون جمله نیست
    """
    title_lower = title.lower()

    # اگه کلمه‌ی exclude توی عنوان بود، skip
    for ex in exclude_words:
        if ex in title:
            return None

    for w in words:
        if w in title or w.lower() in title_lower:
            return w

    return None


def analyze_keywords(items):
    """تحلیل کلمات کلیدی با context"""
    matched = {cat: [] for cat in IRAN_KEYWORDS}

    for item in items:
        title = item["title"]
        for cat, config in IRAN_KEYWORDS.items():
            word = match_keyword_context(
                title,
                config["words"],
                config.get("exclude", []),
            )
            if word:
                matched[cat].append({
                    "title": title[:80],
                    "word": word,
                    "source": item["source"],
                })

    return matched


def analyze_sentiment(items):
    """تحلیل احساسات با کلمات دقیق"""
    pos_count = 0
    neg_count = 0
    pos_titles = []
    neg_titles = []

    for item in items:
        title = item["title"]
        found_pos = None
        found_neg = None

        for word in POSITIVE_IR:
            if word in title:
                found_pos = word
                break

        for word in NEGATIVE_IR:
            if word in title:
                found_neg = word
                break

        if found_pos:
            pos_count += 1
            pos_titles.append(f"[{found_pos}] {title[:70]}")
        elif found_neg:
            neg_count += 1
            neg_titles.append(f"[{found_neg}] {title[:70]}")

    if pos_count > neg_count:
        sentiment = "positive"
    elif neg_count > pos_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "positive_titles": pos_titles[:5],
        "negative_titles": neg_titles[:5],
    }


def main():
    print("\n" + "=" * 60)
    print("  TEST IRAN NEWS FEEDS #2")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")

    all_items = []
    results = {}

    for name, url in IRAN_FEEDS.items():
        items = fetch_feed(name, url)
        results[name] = len(items)
        all_items.extend(items)

    # ═══ خلاصه ═══
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    total = 0
    working = []
    failed = []
    for name, count in results.items():
        if count > 0:
            print(f"✅ {name}: {count}")
            working.append(name)
            total += count
        else:
            print(f"❌ {name}: 0")
            failed.append(name)

    print(f"\n📊 TOTAL: {total} titles")
    print(f"✅ Working: {len(working)}")
    print(f"❌ Failed: {len(failed)}")

    # ═══ تحلیل کلمات کلیدی ═══
    print("\n" + "=" * 60)
    print("  KEYWORD ANALYSIS (context-aware)")
    print("=" * 60)

    keywords_matched = analyze_keywords(all_items)
    total_matches = 0
    for cat, matches in keywords_matched.items():
        if matches:
            total_matches += len(matches)
            print(f"\n🔍 {cat} ({len(matches)}):")
            for m in matches[:3]:
                print(f"  • [{m['word']}] ({m['source']}) {m['title']}")

    print(f"\n📊 TOTAL KEYWORD MATCHES: {total_matches}")

    # ═══ تحلیل احساسات ═══
    print("\n" + "=" * 60)
    print("  SENTIMENT ANALYSIS")
    print("=" * 60)

    sentiment = analyze_sentiment(all_items)
    print(f"Sentiment: {sentiment['sentiment'].upper()}")
    print(f"Positive: {sentiment['positive_count']}")
    print(f"Negative: {sentiment['negative_count']}")

    if sentiment["negative_titles"]:
        print(f"\n⚠️ Negative:")
        for t in sentiment["negative_titles"]:
            print(f"  • {t}")

    if sentiment["positive_titles"]:
        print(f"\n✅ Positive:")
        for t in sentiment["positive_titles"]:
            print(f"  • {t}")

    # ═══ ذخیره ═══
    output = {
        "time": datetime.now().isoformat(),
        "total_titles": total,
        "working_feeds": working,
        "failed_feeds": failed,
        "feeds": results,
        "keywords_matched": {k: len(v) for k, v in keywords_matched.items()},
        "sentiment": sentiment,
        "sample_titles": [item["title"] for item in all_items[:15]],
    }

    with open("iran_news_test2_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Output saved: iran_news_test2_output.json")


if __name__ == "__main__":
    main()
