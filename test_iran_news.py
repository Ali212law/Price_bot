import requests
import json
import re
from datetime import datetime
from xml.etree import ElementTree as ET

# ═══ منابع RSS ایران ═══
IRAN_FEEDS = {
    "iransin": "https://iransin.ir/feed/",
    "shada": "https://shada.ir/feed/",
    "hamshahri": "https://www.hamshahrionline.ir/rss",
    "mehr_economy": "https://www.mehrnews.com/rss/tp/104",
    "ibena": "https://ibena.ir/rss",
}

# ═══ کلمات کلیدی ایران ═══
IRAN_KEYWORDS = {
    "sanctions": ["تحریم", "sanction"],
    "inflation": ["تورم", "inflation"],
    "dollar": ["دلار", "dollar", "ارز"],
    "agreement": ["توافق", "برجام", "مذاکره"],
    "crisis": ["بحران", "اضطراب"],
    "war": ["جنگ", "حمله", "حمله نظامی"],
    "central_bank": ["بانک مرکزی", "نقدینگی"],
    "oil": ["نفت", "پتروشیمی"],
    "gold": ["طلا", "سکه"],
    "crypto": ["کریپتو", "ارز دیجیتال", "بیت‌کوین"],
    "budget": ["بودجه", "مالیات"],
    "subsidy": ["یارانه", "قیمت بنزین"],
}

# ═══ کلمات احساسی ═══
POSITIVE_IR = [
    "توافق", "برجام", "کاهش تحریم", "افزایش صادرات",
    "رشد اقتصادی", "کنترل تورم", "صلح", "مذاکره مثبت",
]
NEGATIVE_IR = [
    "تحریم", "بحران", "جنگ", "افزایش تورم", "کاهش ارزش",
    "احتمال حمله", "فشار", "محدودیت", "قطعنامه",
]


def fetch_feed(name, url):
    """دریافت یه فید RSS"""
    print(f"\n{'='*60}")
    print(f"FETCHING: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"
        })
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")
        print(f"Content-Length: {len(r.content)} bytes")

        if r.status_code != 200:
            print(f"❌ FAILED")
            return []

        try:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            print(f"✅ Parsed XML - {len(items)} items")

            titles = []
            for item in items[:10]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pubdate_elem = item.find("pubDate")

                title = title_elem.text if title_elem is not None else ""
                link = link_elem.text if link_elem is not None else ""
                pubdate = pubdate_elem.text if pubdate_elem is not None else ""

                title = re.sub(r"<[^>]+>", "", title).strip()

                titles.append({
                    "title": title,
                    "link": link,
                    "time": pubdate,
                    "source": name,
                })
                print(f"  • {title[:90]}")

            return titles

        except ET.ParseError as e:
            print(f"⚠️ XML Parse Error: {e}")
            titles = re.findall(r"<title>(.*?)</title>", r.text, re.DOTALL)
            titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles if t.strip()]
            titles = [t for t in titles if len(t) > 10][:10]
            print(f"✅ Regex fallback - {len(titles)} titles")
            return [{"title": t, "link": "", "time": "", "source": name} for t in titles]

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return []


def analyze_keywords(titles):
    """جستجوی کلمات کلیدی در عناوین"""
    matched = {cat: [] for cat in IRAN_KEYWORDS}

    for item in titles:
        title = item["title"]
        for cat, words in IRAN_KEYWORDS.items():
            for word in words:
                if word in title:
                    matched[cat].append({
                        "title": title[:60],
                        "word": word,
                        "source": item["source"],
                    })
                    break

    return matched


def analyze_sentiment(titles):
    """تحلیل احساسات"""
    pos_count = 0
    neg_count = 0
    pos_titles = []
    neg_titles = []

    for item in titles:
        title = item["title"]
        for word in POSITIVE_IR:
            if word in title:
                pos_count += 1
                pos_titles.append(f"[{word}] {title[:60]}")
                break
        for word in NEGATIVE_IR:
            if word in title:
                neg_count += 1
                neg_titles.append(f"[{word}] {title[:60]}")
                break

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
    print("  TEST IRAN NEWS FEEDS")
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
    for name, count in results.items():
        status = "✅" if count > 0 else "❌"
        print(f"{status} {name}: {count} titles")
        total += count
    print(f"\n📊 TOTAL: {total} titles")

    # ═══ تحلیل کلمات کلیدی ═══
    print("\n" + "=" * 60)
    print("  KEYWORD ANALYSIS")
    print("=" * 60)

    keywords_matched = analyze_keywords(all_items)
    for cat, matches in keywords_matched.items():
        if matches:
            print(f"\n🔍 {cat} ({len(matches)}):")
            for m in matches[:3]:
                print(f"  • [{m['word']}] {m['title']}")

    # ═══ تحلیل احساسات ═══
    print("\n" + "=" * 60)
    print("  SENTIMENT ANALYSIS")
    print("=" * 60)

    sentiment = analyze_sentiment(all_items)
    print(f"Sentiment: {sentiment['sentiment'].upper()}")
    print(f"Positive: {sentiment['positive_count']}")
    print(f"Negative: {sentiment['negative_count']}")

    if sentiment["negative_titles"]:
        print(f"\n⚠️ Negative titles:")
        for t in sentiment["negative_titles"]:
            print(f"  • {t}")

    if sentiment["positive_titles"]:
        print(f"\n✅ Positive titles:")
        for t in sentiment["positive_titles"]:
            print(f"  • {t}")

    # ═══ ذخیره ═══
    output = {
        "time": datetime.now().isoformat(),
        "total_titles": total,
        "feeds": results,
        "keywords_matched": {k: len(v) for k, v in keywords_matched.items()},
        "sentiment": sentiment,
        "sample_titles": [item["title"] for item in all_items[:10]],
    }

    with open("iran_news_test_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Output saved: iran_news_test_output.json")


if __name__ == "__main__":
    main()
