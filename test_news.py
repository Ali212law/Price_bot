import requests
import json
import re
from datetime import datetime
from xml.etree import ElementTree as ET

FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "cryptoslate": "https://cryptoslate.com/feed/",
}

# کلمات کلیدی برای sentiment
POSITIVE_WORDS = [
    "surge", "rally", "bullish", "adoption", "etf", "approval",
    "pump", "soar", "gain", "rise", "high", "boost", "breakout",
    "institutional", "support", "positive", "growth", "record",
]

NEGATIVE_WORDS = [
    "crash", "dump", "bearish", "ban", "hack", "exploit",
    "regulation", "lawsuit", "sec", "fraud", "scam", "drop",
    "fall", "plunge", "sell-off", "fear", "warning", "risk",
    "collapse", "liquidation", "bankrupt",
]


def fetch_feed(name, url):
    """دریافت یه RSS feed"""
    print(f"\n{'='*50}")
    print(f"FETCHING: {name}")
    print(f"URL: {url}")
    print(f"{'='*50}")

    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"
        })
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")
        print(f"Content-Length: {len(r.content)} bytes")

        if r.status_code != 200:
            print(f"❌ FAILED")
            return None

        # پارس XML
        try:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            print(f"✅ Parsed XML - {len(items)} items found")

            articles = []
            for item in items[:5]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pubdate_elem = item.find("pubDate")

                title = title_elem.text if title_elem is not None else ""
                link = link_elem.text if link_elem is not None else ""
                pubdate = pubdate_elem.text if pubdate_elem is not None else ""

                # پاک‌سازی title
                title = re.sub(r"<[^>]+>", "", title).strip()

                articles.append({
                    "title": title,
                    "link": link,
                    "time": pubdate,
                })

                print(f"  • {title[:80]}")

            return articles

        except ET.ParseError as e:
            print(f"⚠️ XML Parse Error: {e}")
            # تلاش با regex
            titles = re.findall(r"<title>(.*?)</title>", r.text, re.DOTALL)
            titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles if t.strip()]
            titles = [t for t in titles if len(t) > 10][:5]
            print(f"✅ Regex fallback - {len(titles)} titles")
            for t in titles:
                print(f"  • {t[:80]}")
            return [{"title": t, "link": "", "time": ""} for t in titles]

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return None


def analyze_sentiment(articles):
    """تحلیل ساده sentiment با کلمات کلیدی"""
    if not articles:
        return "neutral", 0, 0, []

    pos_count = 0
    neg_count = 0
    matched = []

    for article in articles:
        title_lower = article["title"].lower()
        for word in POSITIVE_WORDS:
            if word in title_lower:
                pos_count += 1
                matched.append(f"+{word}")
                break
        for word in NEGATIVE_WORDS:
            if word in title_lower:
                neg_count += 1
                matched.append(f"-{word}")
                break

    if pos_count > neg_count:
        sentiment = "positive"
    elif neg_count > pos_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return sentiment, pos_count, neg_count, matched


def main():
    print("\n" + "=" * 50)
    print("  TEST NEWS FEEDS")
    print("=" * 50)
    print(f"Time: {datetime.now().isoformat()}")

    all_articles = []
    results = {}

    for name, url in FEEDS.items():
        articles = fetch_feed(name, url)
        results[name] = {
            "success": articles is not None,
            "count": len(articles) if articles else 0,
        }
        if articles:
            all_articles.extend(articles)

    # تحلیل sentiment
    print("\n" + "=" * 50)
    print("  SENTIMENT ANALYSIS")
    print("=" * 50)

    sentiment, pos, neg, matched = analyze_sentiment(all_articles)
    print(f"Total articles: {len(all_articles)}")
    print(f"Positive words: {pos}")
    print(f"Negative words: {neg}")
    print(f"Sentiment: {sentiment.upper()}")
    print(f"Matched words: {matched[:20]}")

    # خلاصه
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)
    for name, r in results.items():
        status = "✅" if r["success"] else "❌"
        print(f"{status} {name}: {r['count']} articles")

    # ذخیره نمونه (فقط برای دیباگ)
    output = {
        "time": datetime.now().isoformat(),
        "total_articles": len(all_articles),
        "sentiment": sentiment,
        "positive_count": pos,
        "negative_count": neg,
        "feeds": results,
        "sample_titles": [a["title"] for a in all_articles[:5]],
    }

    with open("news_test_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Output saved: news_test_output.json")


if __name__ == "__main__":
    main()
