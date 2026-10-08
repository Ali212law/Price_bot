import asyncio
import websockets
import json
import os
import base64
import time
import uuid
import socket
import re
import requests
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
ABAN_API_KEY = os.environ.get("ABAN_API_KEY", "")

HISTORY_FILE = "dollar_history.json"
BTC_HISTORY_FILE = "btc_history.json"
PAPER_TRADES_FILE = "paper_trades.json"
SHADOW_TRADES_FILE = "shadow_trades.json"
PRICE_COMPARISON_FILE = "price_comparison.json"
NEWS_HISTORY_FILE = "news_history.json"
VETO_LOG_FILE = "veto_log.json"
IRAN_NEWS_FILE = "iran_news_data.json"
PRICE_COMPONENTS_FILE = "price_components.json"
LOCK_FILE = "lock.json"

CODE_VERSION = "paper_trade32"

LOCK_MAX_AGE_SECONDS = 720

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

IRR_TO_TOMAN = 10
PRICE_UNIT_THRESHOLD = 100_000_000_000

MAX_RISK_TABLE = {
    "VERY_STRONG": 1000, "STRONG": 750, "DIP": 700,
    "MOMENTUM": 600, "MEDIUM": 500, "TOP": 400,
    "SIMPLE_STRONG": 300, "SIMPLE_MEDIUM": 200,
}
DEFAULT_MAX_RISK = 300

MAX_TRADE_TOMAN = 50000
MIN_TRADE_TOMAN = 5000
MAX_DAILY_TRADES = 5
MAX_OPEN_POSITIONS = 2
MAX_SHADOW_TRADES = 500

STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3.0
EFFECTIVE_RISK_PERCENT = STOP_LOSS_PERCENT + TOTAL_COST_PERCENT

BTC_LOOKBACK_SHORT = 6
BTC_LOOKBACK_LONG = 24
MAX_DATA_AGE_SECONDS = 300

WALLEX_OHLC_URL = "https://api.wallex.ir/v1/udf/history"
WALLEX_OHLC_RESOLUTION = "1"
WALLEX_OHLC_HOURS = 24
WALLEX_OHLC_BUCKET_SEC = 900
WALLEX_OHLC_MIN_BUCKET_RECORDS = 10

RSI_PERIOD = 14
MIN_RESAMPLED_RECORDS = 20
RSI_RESAMPLE_MINUTES = 15

RSI_COVERAGE_VALID_HIGH = 90.0
RSI_COVERAGE_VALID_LOW = 80.0
RSI_COVERAGE_MIN = 50.0

THRESHOLD_VERY_STRONG = 1.5
THRESHOLD_STRONG = 1.0
THRESHOLD_MEDIUM = 0.5
THRESHOLD_MOMENTUM = 2.0

RSI_OVERSOLD = 30
RSI_LOW = 35
RSI_MILD_LOW = 45
RSI_MILD_HIGH = 65
RSI_HIGH = 70
RSI_OVERBOUGHT = 75

TOP_TREND_FILTER_ENABLED = True
TOP_TREND_CHG6H_THRESHOLD = 0.0

EMA_FAST_PERIOD = 9
EMA_SLOW_PERIOD = 21
VOLUME_LOOKBACK_BUCKETS = 96
DOLLAR_HISTORY_MAX_HOURS = 48

NOBITEX_WS_URL = "wss://ws.nobitex.ir/connection/websocket"
WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"
WALLEX_USDT_SYMBOL = "USDTTMN"

BINANCE_API_URL = "https://api.binance.com"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

ABAN_IP = "185.143.234.130"
ABAN_HOST = "api.abantether.com"
ABAN_TICKER_URL = f"https://{ABAN_HOST}/api/v1/manager/otc/ticker"

SIGNAL_PRIORITY = [
    "VERY_STRONG", "STRONG", "DIP", "MOMENTUM",
    "MEDIUM", "TOP", "SIMPLE_STRONG", "SIMPLE_MEDIUM",
]

NEWS_FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "cryptoslate": "https://cryptoslate.com/feed/",
}

POSITIVE_WORDS = [
    "surge", "rally", "bullish", "adoption", "etf", "approval",
    "pump", "soar", "gain", "rise", "high", "boost", "breakout",
    "institutional", "support", "positive", "growth", "record",
    "buy", "long", "up", "jump", "recover", "bullrun",
]

NEGATIVE_WORDS = [
    "crash", "dump", "bearish", "ban", "hack", "exploit",
    "regulation", "lawsuit", "sec", "fraud", "scam", "drop",
    "fall", "plunge", "sell-off", "fear", "warning", "risk",
    "collapse", "liquidation", "bankrupt", "short", "down",
    "loss", "attack", "exploit", "steal", "rug",
]

VETO_MULTIPLIER = 2.0
IRAN_IMPACT_MULTIPLIER = 2.0

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این Paper Trading است. معامله واقعی انجام نمی‌شود."

_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, *args, **kwargs):
    if host == ABAN_HOST:
        return _original_getaddrinfo(ABAN_IP, *args, **kwargs)
    return _original_getaddrinfo(host, *args, **kwargs)

socket.getaddrinfo = _patched_getaddrinfo


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def normalize_price_unit(value):
    try:
        v = float(value)
        if v > PRICE_UNIT_THRESHOLD:
            return v / IRR_TO_TOMAN
        return v
    except (TypeError, ValueError):
        return value


def calculate_position_size(signal_type):
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    size = risk_toman / (EFFECTIVE_RISK_PERCENT / 100)
    size = min(size, MAX_TRADE_TOMAN)
    if size < MIN_TRADE_TOMAN:
        return None
    return round(size, 0)


def compute_rsi_validity(rsi, rsi_source, rsi_report):
    if rsi is None:
        return False, "no_rsi", 0.0
    if rsi_source == "wallex_failed":
        return False, "wallex_failed", 0.0
    coverage = float(rsi_report.get("coverage_pct", 0) or 0)
    if coverage >= RSI_COVERAGE_VALID_HIGH:
        return True, "high", coverage
    if coverage >= RSI_COVERAGE_VALID_LOW:
        return True, "medium_with_warning", coverage
    if coverage >= RSI_COVERAGE_MIN:
        return False, "low_invalid", coverage
    return False, "critical_invalid", coverage


def get_wallex_ohlc_1m(hours=WALLEX_OHLC_HOURS):
    try:
        now = int(time.time())
        from_ts = now - hours * 3600
        params = {
            "symbol": WALLEX_SYMBOL,
            "resolution": WALLEX_OHLC_RESOLUTION,
            "from": from_ts,
            "to": now,
        }
        r = requests.get(WALLEX_OHLC_URL, params=params, timeout=20)
        if r.status_code != 200:
            print(f"  [WALLEX-OHLC] HTTP {r.status_code}")
            return None
        data = r.json()
        if data.get("s") != "ok":
            print(f"  [WALLEX-OHLC] status={data.get('s')}")
            return None

        t = data.get("t", [])
        o = data.get("o", [])
        h = data.get("h", [])
        l = data.get("l", [])
        c = data.get("c", [])
        v = data.get("v", [])

        n = min(len(t), len(o), len(h), len(l), len(c))
        if n < 100:
            print(f"  [WALLEX-OHLC] insufficient rows: {n}")
            return None

        sample_close = float(c[0]) if c else 0
        if sample_close > PRICE_UNIT_THRESHOLD:
            unit_divisor = IRR_TO_TOMAN
            unit_label = "IRR→TMN"
        else:
            unit_divisor = 1
            unit_label = "TMN"
        print(f"  [WALLEX-OHLC] unit: sample_close={sample_close:,.0f} → {unit_label}")

        candles = []
        for i in range(n):
            try:
                candles.append({
                    "t": int(t[i]),
                    "o": float(o[i]) / unit_divisor,
                    "h": float(h[i]) / unit_divisor,
                    "l": float(l[i]) / unit_divisor,
                    "c": float(c[i]) / unit_divisor,
                    "v": float(v[i]) if i < len(v) else 0.0,
                })
            except (ValueError, TypeError, IndexError):
                continue

        candles.sort(key=lambda x: x["t"])
        print(f"  [WALLEX-OHLC] fetched {len(candles)} 1-min candles "
              f"({candles[0]['t']} → {candles[-1]['t']})")
        return candles
    except Exception as e:
        print(f"  [WALLEX-OHLC] ERROR: {e}")
        return None


def resample_1m_to_15m_ohlcv(candles_1m):
    if not candles_1m:
        return [], {}

    buckets = {}
    for c in candles_1m:
        bucket_ts = (c["t"] // WALLEX_OHLC_BUCKET_SEC) * WALLEX_OHLC_BUCKET_SEC
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {
                "t": bucket_ts,
                "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"],
                "count": 1,
            }
        else:
            b = buckets[bucket_ts]
            b["h"] = max(b["h"], c["h"])
            b["l"] = min(b["l"], c["l"])
            b["c"] = c["c"]
            b["v"] += c["v"]
            b["count"] += 1

    sorted_buckets = sorted(buckets.values(), key=lambda x: x["t"])

    if len(sorted_buckets) >= 2:
        first_t = sorted_buckets[0]["t"]
        last_t = sorted_buckets[-1]["t"]
        total_span = last_t - first_t
        expected = (total_span // WALLEX_OHLC_BUCKET_SEC) + 1
    else:
        expected = len(sorted_buckets)

    valid = [b for b in sorted_buckets
             if b["count"] >= WALLEX_OHLC_MIN_BUCKET_RECORDS]

    if valid and (int(time.time()) - valid[-1]["t"]) < WALLEX_OHLC_BUCKET_SEC:
        valid = valid[:-1]

    coverage = round(len(valid) / expected * 100, 1) if expected else 0.0

    report = {
        "source": "wallex_ohlc",
        "timeframe": "15m",
        "hours": WALLEX_OHLC_HOURS,
        "candles_1m": len(candles_1m),
        "buckets_total": len(sorted_buckets),
        "buckets_valid": len(valid),
        "buckets_expected": expected,
        "coverage_pct": coverage,
        "min_records_per_bucket": WALLEX_OHLC_MIN_BUCKET_RECORDS,
    }
    return valid, report


def get_rsi_from_wallex_ohlc(hours=WALLEX_OHLC_HOURS):
    candles_1m = get_wallex_ohlc_1m(hours=hours)
    if not candles_1m:
        return None, "wallex_failed", {"source": "wallex_failed", "coverage_pct": 0.0}

    buckets_15m, report = resample_1m_to_15m_ohlcv(candles_1m)

    print(f"  [RSI] Wallex OHLC: 1m={report['candles_1m']} | "
          f"15m={report['buckets_valid']}/{report['buckets_expected']} | "
          f"coverage={report['coverage_pct']}%")

    if len(buckets_15m) < MIN_RESAMPLED_RECORDS:
        print(f"  [RSI] insufficient 15m buckets: {len(buckets_15m)}")
        return None, "wallex_insufficient", report

    prices = [b["c"] for b in buckets_15m]
    rsi = calculate_rsi(prices, RSI_PERIOD)
    if rsi is None:
        return None, "wallex_calc_failed", report

    print(f"  [RSI] Wallex OHLC calculated: {rsi} (from {len(prices)} closes)")
    return rsi, "wallex_ohlc", report


def resample_history(btc_history, interval_minutes=RSI_RESAMPLE_MINUTES):
    if not btc_history or len(btc_history) < 2:
        return btc_history, {}
    sorted_hist = sorted(btc_history, key=lambda x: x[0])
    resampled = []
    current_bucket = None
    bucket_last_price = None
    for t, p in sorted_hist:
        bucket_minute = (t.minute // interval_minutes) * interval_minutes
        bucket_start = t.replace(minute=bucket_minute, second=0, microsecond=0)
        if current_bucket is None or bucket_start != current_bucket:
            if bucket_last_price is not None:
                resampled.append((current_bucket, bucket_last_price))
            current_bucket = bucket_start
        bucket_last_price = p
    if bucket_last_price is not None:
        resampled.append((current_bucket, bucket_last_price))

    first_ts = sorted_hist[0][0]
    last_ts = sorted_hist[-1][0]
    total_minutes = (last_ts - first_ts).total_seconds() / 60
    expected = int(total_minutes / interval_minutes) + 1
    coverage = round(len(resampled) / expected * 100, 1) if expected else 0
    return resampled, {
        "source": "btc_history_legacy",
        "resampled_candles": len(resampled),
        "expected_candles": expected,
        "coverage_pct": coverage,
    }


def get_legacy_rsi_from_btc_history(btc_history):
    if not btc_history:
        return None, "none", {}
    resampled, report = resample_history(btc_history, RSI_RESAMPLE_MINUTES)
    if len(resampled) < MIN_RESAMPLED_RECORDS:
        return None, "none", report
    prices = [p for _, p in resampled]
    return calculate_rsi(prices, RSI_PERIOD), "btc_history_legacy", report


def calculate_rsi(prices, period=RSI_PERIOD):
    if not prices or len(prices) < period + 1:
        return None
    try:
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change); losses.append(0)
            else:
                gains.append(0); losses.append(abs(change))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)
    except:
        return None


def calculate_ema(prices, period):
    if not prices or len(prices) < period:
        return None
    try:
        k = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = p * k + ema * (1 - k)
        return round(ema, 2)
    except Exception:
        return None


def get_dollar_change_and_update_history(wallex_data, now):
    result = {
        "dollar_6h_change_pct": None,
        "dollar_24h_change_pct": None,
        "dollar_last": None,
        "dollar_history_size": 0,
    }
    try:
        usdt_last = normalize_price_unit(wallex_data["usdt"]["last"])
        if usdt_last <= 0:
            return result

        result["dollar_last"] = usdt_last

        data, sha = load_from_github(HISTORY_FILE)
        history = data if data else []
        if history and not isinstance(history[0], list):
            history = []

        history.append([now.isoformat(), usdt_last])

        cutoff = now - timedelta(hours=DOLLAR_HISTORY_MAX_HOURS)
        clean = []
        for item in history:
            try:
                t = datetime.fromisoformat(item[0])
                if t >= cutoff:
                    clean.append(item)
            except Exception:
                continue
        history = clean
        result["dollar_history_size"] = len(history)

        if len(history) >= 2:
            cutoff_6h = now - timedelta(hours=6)
            past_6h = [p for t_str, p in history
                       if datetime.fromisoformat(t_str) <= cutoff_6h]
            if past_6h:
                oldest_6h = past_6h[0]
                if oldest_6h > 0:
                    result["dollar_6h_change_pct"] = round(
                        (usdt_last - oldest_6h) / oldest_6h * 100, 4
                    )

            cutoff_24h = now - timedelta(hours=24)
            past_24h = [p for t_str, p in history
                        if datetime.fromisoformat(t_str) <= cutoff_24h]
            if past_24h:
                oldest_24h = past_24h[0]
                if oldest_24h > 0:
                    result["dollar_24h_change_pct"] = round(
                        (usdt_last - oldest_24h) / oldest_24h * 100, 4
                    )

        save_to_github(HISTORY_FILE, history, sha)
    except Exception as e:
        print(f"  [DOLLAR] ERROR: {e}")
    return result


def compute_metadata_extras(candles_15m, wallex_data, now):
    extras = {
        "volume_current_15m": None,
        "volume_avg_15m_24h": None,
        "volume_ratio": None,
        "ema9_15m": None,
        "ema21_15m": None,
        "ema_state": None,
    }
    try:
        if not candles_15m or len(candles_15m) < EMA_SLOW_PERIOD:
            return extras

        last_bucket = candles_15m[-1]
        extras["volume_current_15m"] = round(last_bucket["v"], 2)

        recent = candles_15m[-VOLUME_LOOKBACK_BUCKETS:]
        if recent:
            avg_vol = sum(b["v"] for b in recent) / len(recent)
            extras["volume_avg_15m_24h"] = round(avg_vol, 2)
            if avg_vol > 0:
                extras["volume_ratio"] = round(last_bucket["v"] / avg_vol, 3)

        closes = [b["c"] for b in candles_15m]
        ema9 = calculate_ema(closes, EMA_FAST_PERIOD)
        ema21 = calculate_ema(closes, EMA_SLOW_PERIOD)
        extras["ema9_15m"] = ema9
        extras["ema21_15m"] = ema21
        if ema9 is not None and ema21 is not None:
            extras["ema_state"] = "bull" if ema9 > ema21 else "bear"
    except Exception as e:
        print(f"  [EXTRAS] ERROR: {e}")
    return extras


def get_iran_news_impact():
    data, _ = load_from_github(IRAN_NEWS_FILE)
    if not data:
        print("IRAN_NEWS: not available")
        return {
            "iran_count": 0, "up": 0, "down": 0, "unclear": 0,
            "sentiment": "unclear", "fx_count": 0, "top_events": {},
            "source": "no_data",
        }

    stats = {}
    items = []
    if isinstance(data, dict):
        stats = data.get("stats", {})
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data

    if stats and "by_btc_impact" in stats:
        up = stats["by_btc_impact"].get("up", 0)
        down = stats["by_btc_impact"].get("down", 0)
        unclear = stats["by_btc_impact"].get("unclear", 0)
        fx_count = stats.get("by_event", {}).get("fx", 0)
        iran_count = stats.get("recent_news_24h")
        if iran_count is None:
            iran_count = stats.get("unique_by_hash", 0)
        top_events = stats.get("by_event", {})
        source = "stats"
    else:
        dict_items = [it for it in items if isinstance(it, dict)]
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = [it for it in dict_items if (it.get("fetched_at") or "") >= cutoff]
        if len(recent) < 20:
            recent = dict_items[:200]
        up = down = unclear = fx_count = 0
        top_events = {}
        for it in recent:
            imp = it.get("btc_impact", "unclear")
            if imp == "up": up += 1
            elif imp == "down": down += 1
            else: unclear += 1
            ev = it.get("primary_event")
            if ev:
                top_events[ev] = top_events.get(ev, 0) + 1
                if ev == "fx": fx_count += 1
        iran_count = len(recent)
        source = "computed"

    if up > down * IRAN_IMPACT_MULTIPLIER and up >= 3:
        sentiment = "bullish"
    elif down > up * IRAN_IMPACT_MULTIPLIER and down >= 3:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "iran_count": iran_count, "up": up, "down": down,
        "unclear": unclear, "sentiment": sentiment,
        "fx_count": fx_count, "top_events": top_events, "source": source,
    }


def apply_iran_warning(side, iran_impact):
    if side is None:
        return False, "no signal"
    sentiment = iran_impact["sentiment"]
    if side == "sell" and sentiment == "bullish":
        return True, f"IRAN WARNING: bullish Iran + SELL (up={iran_impact['up']}, down={iran_impact['down']})"
    if side == "buy" and sentiment == "bearish":
        return True, f"IRAN WARNING: bearish Iran + BUY (up={iran_impact['up']}, down={iran_impact['down']})"
    return False, "OK"


def fetch_news_feed(name, url):
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"
        })
        if r.status_code != 200:
            return []
        try:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            titles = []
            for item in items[:10]:
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    title = re.sub(r"<[^>]+>", "", title_elem.text).strip()
                    titles.append(title)
            return titles
        except ET.ParseError:
            titles = re.findall(r"<title>(.*?)</title>", r.text, re.DOTALL)
            titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles if t.strip()]
            return [t for t in titles if len(t) > 15][:10]
    except Exception as e:
        print(f"NEWS {name} ERROR: {e}")
        return []


def get_all_news():
    all_titles = []
    feed_counts = {}
    for name, url in NEWS_FEEDS.items():
        titles = fetch_news_feed(name, url)
        feed_counts[name] = len(titles)
        all_titles.extend(titles)
    return all_titles, feed_counts


def analyze_sentiment(titles):
    if not titles:
        return {"sentiment": "neutral", "pos": 0, "neg": 0, "matched": []}
    pos_count = neg_count = 0
    matched = []
    for title in titles:
        title_lower = title.lower()
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
    if pos_count > neg_count: sentiment = "positive"
    elif neg_count > pos_count: sentiment = "negative"
    else: sentiment = "neutral"
    return {"sentiment": sentiment, "pos": pos_count, "neg": neg_count, "matched": matched[:10]}


def apply_news_veto(side, sentiment_data):
    if side is None:
        return False, "no signal"
    sentiment = sentiment_data["sentiment"]
    pos = sentiment_data["pos"]
    neg = sentiment_data["neg"]
    if side == "buy" and sentiment == "negative":
        if neg > pos * VETO_MULTIPLIER:
            return True, f"GLOBAL NEWS VETO BUY (neg={neg} > pos×{VETO_MULTIPLIER})"
    if side == "sell" and sentiment == "positive":
        if pos > neg * VETO_MULTIPLIER:
            return True, f"GLOBAL NEWS VETO SELL (pos={pos} > neg×{VETO_MULTIPLIER})"
    return False, "OK"


def save_news_history(sentiment_data, feed_counts, titles, now):
    try:
        entry = {
            "time": now.isoformat(),
            "sentiment": sentiment_data["sentiment"],
            "pos": sentiment_data["pos"],
            "neg": sentiment_data["neg"],
            "total_titles": len(titles),
            "feed_counts": feed_counts,
            "sample_titles": titles[:5],
        }
        data, sha = load_from_github(NEWS_HISTORY_FILE)
        history = data if data else []
        history.append(entry)
        cutoff = (now - timedelta(days=7)).isoformat()
        history = [h for h in history if h.get("time", "") >= cutoff]
        history = history[-500:]
        save_to_github(NEWS_HISTORY_FILE, history, sha)
    except Exception as e:
        print(f"NEWS_HISTORY ERROR: {e}")


def get_wallex_prices():
    try:
        url = f"{WALLEX_API_URL}/v1/markets"
        fetch_start = datetime.now()
        r = request_with_retry(url, max_retries=3, timeout=15)
        if not r:
            return None
        fetch_end = datetime.now()
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = symbols.get(WALLEX_SYMBOL, {})
        usdt = symbols.get(WALLEX_USDT_SYMBOL, {})
        btc_stats = btc.get("stats", {})
        usdt_stats = usdt.get("stats", {})
        if not btc_stats:
            return None

        btc_last_raw = float(btc_stats.get("lastPrice", 0))
        btc_bid_raw = float(btc_stats.get("bidPrice", 0))
        btc_ask_raw = float(btc_stats.get("askPrice", 0))
        usdt_last_raw = float(usdt_stats.get("lastPrice", 0)) if usdt_stats else 0
        usdt_bid_raw = float(usdt_stats.get("bidPrice", 0)) if usdt_stats else 0
        usdt_ask_raw = float(usdt_stats.get("askPrice", 0)) if usdt_stats else 0

        unit_div = IRR_TO_TOMAN if btc_last_raw > PRICE_UNIT_THRESHOLD else 1
        unit_label = "IRR→TMN" if unit_div > 1 else "TMN"

        btc_last = btc_last_raw / unit_div
        btc_bid = btc_bid_raw / unit_div
        btc_ask = btc_ask_raw / unit_div
        usdt_div = IRR_TO_TOMAN if usdt_last_raw > 1_000_000 else 1
        usdt_last = usdt_last_raw / usdt_div
        usdt_bid = usdt_bid_raw / usdt_div
        usdt_ask = usdt_ask_raw / usdt_div

        data_age = (fetch_end - fetch_start).total_seconds()
        print(f"WALLEX BTC: last={btc_last:,.0f} | bid={btc_bid:,.0f} | ask={btc_ask:,.0f}  [{unit_label}]")
        print(f"WALLEX USDT: last={usdt_last:,.0f}")
        if data_age > MAX_DATA_AGE_SECONDS:
            return None
        return {
            "btc": {"last": btc_last, "bid": btc_bid, "ask": btc_ask},
            "usdt": {"last": usdt_last, "bid": usdt_bid, "ask": usdt_ask},
            "fetch_end": fetch_end.isoformat(),
            "data_age_seconds": round(data_age, 2),
        }
    except Exception as e:
        print(f"WALLEX ERROR: {e}")
        return None


def get_btc_usdt():
    try:
        r = requests.get(
            f"{BINANCE_API_URL}/api/v3/ticker/bookTicker",
            params={"symbol": "BTCUSDT"}, timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            bid = float(data.get("bidPrice", 0))
            ask = float(data.get("askPrice", 0))
            mid = (bid + ask) / 2
            print(f"BINANCE BTC/USDT: {mid:,.2f}")
            return {"last": mid, "bid": bid, "ask": ask, "source": "binance"}
    except Exception as e:
        print(f"BINANCE ERROR: {e}")
    try:
        r = requests.get(
            f"{COINGECKO_API_URL}/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=10,
        )
        if r.status_code == 200:
            price = float(r.json().get("bitcoin", {}).get("usd", 0))
            print(f"COINGECKO BTC/USDT: {price:,.2f}")
            return {"last": price, "bid": price, "ask": price, "source": "coingecko"}
    except Exception as e:
        print(f"COINGECKO ERROR: {e}")
    return None


async def run_nobitex_ws():
    try:
        async with websockets.connect(
            NOBITEX_WS_URL, open_timeout=15, close_timeout=5,
            ping_interval=20, ping_timeout=20,
        ) as ws:
            await ws.send('{"connect": {}, "id": 1}')
            await asyncio.wait_for(ws.recv(), timeout=10)
            await ws.send(json.dumps({
                "subscribe": {"channel": "public:orderbook-BTCIRT"}, "id": 2
            }))
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=20)
                    data = json.loads(msg)
                    if "push" in data:
                        asks = data["push"]["pub"]["data"]["asks"]
                        bids = data["push"]["pub"]["data"]["bids"]
                        best_ask = float(asks[0][0]) / IRR_TO_TOMAN
                        best_bid = float(bids[0][0]) / IRR_TO_TOMAN
                        mid = (best_ask + best_bid) / 2
                        return {"last": mid, "bid": best_bid, "ask": best_ask}
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        print(f"NOBITEX WS ERROR: {e}")
    return None


async def get_nobitex_price(max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return await run_nobitex_ws()
        except Exception:
            pass
        if attempt < max_attempts - 1:
            await asyncio.sleep(3)
    return None


def get_aban_price():
    if not ABAN_API_KEY:
        return None
    try:
        headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}
        r = requests.get(ABAN_TICKER_URL, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        btc = data.get("data", {}).get("markets", {}).get("BTCIRT", {})
        if not btc:
            return None
        buy = float(btc.get("buy_price", 0))
        sell = float(btc.get("sell_price", 0))
        mid = (buy + sell) / 2
        return {"buy": buy, "sell": sell, "mid": mid}
    except Exception as e:
        print(f"ABAN ERROR: {e}")
        return None


def save_price_comparison(wallex, nobitex, aban, btc_usdt, now):
    if not wallex:
        return
    try:
        btc = wallex["btc"]
        usdt = wallex["usdt"]
        entry = {
            "time": now.isoformat(),
            "wallex_btc_last": btc["last"],
            "wallex_btc_bid": btc["bid"],
            "wallex_btc_ask": btc["ask"],
            "wallex_usdt_last": usdt["last"],
        }
        if btc_usdt:
            entry["btc_usdt"] = btc_usdt["last"]
            entry["btc_usdt_source"] = btc_usdt["source"]
            if usdt["last"] > 0:
                implied = btc_usdt["last"] * usdt["last"]
                diff = btc["last"] - implied
                diff_pct = (diff / implied) * 100 if implied else 0
                entry["implied_btc_tmn"] = round(implied, 0)
                entry["diff_vs_wallex_pct"] = round(diff_pct, 4)
        if nobitex:
            diff_wn = nobitex["bid"] - btc["ask"]
            entry["wallex_to_nobitex"] = round(diff_wn, 0)
            entry["wallex_to_nobitex_pct"] = round((diff_wn / btc["ask"]) * 100, 4)
        if aban:
            diff_wa = aban["sell"] - btc["ask"]
            entry["wallex_to_aban"] = round(diff_wa, 0)
            entry["wallex_to_aban_pct"] = round((diff_wa / btc["ask"]) * 100, 4)

        data, sha = load_from_github(PRICE_COMPARISON_FILE)
        history = data if data else []
        history.append(entry)
        cutoff = (now - timedelta(days=7)).isoformat()
        history = [h for h in history if h.get("time", "") >= cutoff]
        save_to_github(PRICE_COMPARISON_FILE, history, sha)
        print("COMPARISON SAVED")

        comp_entry = {
            "time": now.isoformat(),
            "btc_tmn": btc["last"],
            "usdt_tmn": usdt["last"],
            "btc_usdt": btc_usdt["last"] if btc_usdt else 0,
            "implied_btc_tmn": entry.get("implied_btc_tmn"),
            "diff_pct": entry.get("diff_vs_wallex_pct"),
        }
        comp_data, comp_sha = load_from_github(PRICE_COMPONENTS_FILE)
        comp_history = comp_data if comp_data else []
        comp_history.append(comp_entry)
        comp_history = [h for h in comp_history if h.get("time", "") >= cutoff]
        save_to_github(PRICE_COMPONENTS_FILE, comp_history, comp_sha)
    except Exception as e:
        print(f"COMPARISON ERROR: {e}")


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
        print(f"LOAD ERROR ({filename}): {e}")
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
        print(f"SAVE ERROR ({filename}): {e}")
        return False


def request_with_retry(url, headers=None, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in (200, 404):
                return r
            print(f"RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries} - Error: {e}")
        if attempt < max_retries - 1:
            time.sleep(3 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
            print(f"PUT RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"PUT RETRY {attempt+1}/{max_retries} - Error: {e}")
        if attempt < max_retries - 1:
            time.sleep(3 ** attempt)
    return None


def acquire_lock():
    try:
        lock_data, lock_sha = load_from_github(LOCK_FILE)
        now = datetime.now()
        if lock_data:
            try:
                lock_time = datetime.fromisoformat(lock_data.get("time", "2000-01-01"))
                age = (now - lock_time).total_seconds()
                if age < LOCK_MAX_AGE_SECONDS:
                    print(f"LOCK EXISTS ({age:.0f}s) - SKIP")
                    return False
            except Exception:
                pass
        new_lock = {"time": now.isoformat(), "id": str(uuid.uuid4())}
        ok = save_to_github(LOCK_FILE, new_lock, lock_sha)
        if not ok:
            print("LOCK SAVE FAILED - SKIP")
            return False
        print("LOCK ACQUIRED")
        return True
    except Exception as e:
        print(f"LOCK ERROR: {e}")
        return False


def release_lock():
    try:
        _, lock_sha = load_from_github(LOCK_FILE)
        if lock_sha:
            url = f"https://api.github.com/repos/{GH_REPO}/contents/{LOCK_FILE}"
            headers = {"Authorization": f"token {GH_TOKEN}"}
            payload = {"message": "Release lock", "sha": lock_sha}
            requests.delete(url, headers=headers, json=payload, timeout=30)
            print("LOCK RELEASED")
    except Exception as e:
        print(f"RELEASE ERROR: {e}")


def calculate_btc_change(btc_history, current_price, now, lookback_hours):
    if not btc_history or current_price is None:
        return 0.0
    lookback_time = now - timedelta(hours=lookback_hours)
    recent = [(t, p) for t, p in btc_history if t >= lookback_time]
    print(f"  [BTC-CHANGE] lookback={lookback_hours}h, records={len(recent)}")
    if len(recent) >= 1:
        avg_old = sum(p for _, p in recent) / len(recent)
        change = ((current_price - avg_old) / avg_old) * 100
        print(f"  [BTC-CHANGE] change={change:+.4f}%")
        return change
    return 0.0


def classify_signal_btc(btc_change_6h, btc_change_24h, rsi, rsi_valid=True):
    if rsi is None:
        rsi = 50
    buy_signals = []
    sell_signals = []

    if btc_change_6h >= THRESHOLD_MOMENTUM:
        buy_signals.append("MOMENTUM")
    if btc_change_6h <= -THRESHOLD_MOMENTUM:
        sell_signals.append("MOMENTUM")

    if rsi_valid:
        if rsi < RSI_OVERSOLD and btc_change_6h >= THRESHOLD_VERY_STRONG:
            buy_signals.append("VERY_STRONG")
        if rsi < RSI_LOW and btc_change_6h >= THRESHOLD_STRONG:
            buy_signals.append("STRONG")
        if rsi < RSI_MILD_LOW and btc_change_6h >= THRESHOLD_MEDIUM:
            buy_signals.append("MEDIUM")
        if rsi < RSI_OVERSOLD:
            buy_signals.append("DIP")
        if rsi > RSI_OVERBOUGHT and btc_change_6h <= -THRESHOLD_VERY_STRONG:
            sell_signals.append("VERY_STRONG")
        if rsi > RSI_HIGH and btc_change_6h <= -THRESHOLD_STRONG:
            sell_signals.append("STRONG")
        if rsi > RSI_MILD_HIGH and btc_change_6h <= -THRESHOLD_MEDIUM:
            sell_signals.append("MEDIUM")
        if rsi > RSI_OVERBOUGHT:
            sell_signals.append("TOP")
    else:
        print(f"  [RSI-INVALID] RSI-based signals suppressed (rsi={rsi}, rsi_valid=False)")

    if buy_signals and sell_signals:
        print(f"CONFLICT! → NO TRADE")
        return "CONFLICT", None
    signals = [("buy", s) for s in buy_signals] + [("sell", s) for s in sell_signals]
    if not signals:
        return None, None
    for priority_signal in SIGNAL_PRIORITY:
        for side, sig in signals:
            if sig == priority_signal:
                return side, sig
    return signals[0]


def has_open_position_in_direction(trades, side):
    side = side.lower()
    return any(
        t.get("status") == "open" and t.get("side", "").lower() == side
        for t in trades
    )


def count_open_positions(trades):
    return len([t for t in trades if t.get("status") == "open"])


def can_open_new_position(trades, side):
    side = side.lower()
    if has_open_position_in_direction(trades, side):
        return False, f"ALREADY_OPEN_{side.upper()}"
    open_count = count_open_positions(trades)
    if open_count >= MAX_OPEN_POSITIONS:
        return False, f"MAX_OPEN_{MAX_OPEN_POSITIONS}"
    return True, "OK"


def build_metadata(wallex_data, news_sentiment, iran_impact,
                   rsi, rsi_source, rsi_report,
                   rsi_valid, rsi_validity_status,
                   legacy_rsi, legacy_source, legacy_report,
                   extras):
    return {
        "code_version": CODE_VERSION,
        "run_time": datetime.now().isoformat(),
        "rsi_source": rsi_source,
        "rsi_value": rsi,
        "rsi_report": rsi_report,
        "rsi_valid": rsi_valid,
        "rsi_validity_status": rsi_validity_status,
        "rsi_coverage_pct": rsi_report.get("coverage_pct") if rsi_report else None,
        "rsi_timeframe": rsi_report.get("timeframe") if rsi_report else None,
        "legacy_rsi_value": legacy_rsi,
        "legacy_rsi_source": legacy_source,
        "legacy_rsi_coverage_pct": legacy_report.get("coverage_pct") if legacy_report else None,
        "news_global_sentiment": news_sentiment["sentiment"],
        "news_global_pos": news_sentiment["pos"],
        "news_global_neg": news_sentiment["neg"],
        "iran_news_count": iran_impact["iran_count"],
        "iran_up": iran_impact["up"],
        "iran_down": iran_impact["down"],
        "iran_sentiment": iran_impact["sentiment"],
        "iran_fx_count": iran_impact["fx_count"],
        "iran_source": iran_impact.get("source", "unknown"),
        "wallex_btc_last": wallex_data["btc"]["last"],
        "wallex_usdt_last": wallex_data["usdt"]["last"],
        "extras": extras,
    }


def make_trade(side, entry_price, signal_type, btc_change_6h, rsi,
               amount_toman, metadata, shadow_type=None, reason=None):
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    if side.lower() == "buy":
        stop_price = entry_price * (1 - STOP_LOSS_PERCENT / 100)
        target_price = entry_price * (1 + TAKE_PROFIT_PERCENT / 100)
    else:
        stop_price = entry_price * (1 + STOP_LOSS_PERCENT / 100)
        target_price = entry_price * (1 - TAKE_PROFIT_PERCENT / 100)
    now = datetime.now()
    base = {
        "date": now.date().isoformat(),
        "time": now.isoformat(),
        "entry_time": now.isoformat(),
        "side": side,
        "signal_type": signal_type,
        "exchange": "wallex",
        "symbol": WALLEX_SYMBOL,
        "btc_change_6h_at_entry": round(btc_change_6h, 2),
        "rsi_at_entry": rsi,
        "entry_price": entry_price,
        "entry_price_toman": entry_price,
        "entry_price_irr": entry_price * IRR_TO_TOMAN,
        "irr_to_toman": IRR_TO_TOMAN,
        "stop_price": stop_price,
        "target_price": target_price,
        "take_profit_price": target_price,
        "amount_toman": amount_toman,
        "max_risk_toman": risk_toman,
        "stop_loss_percent": STOP_LOSS_PERCENT,
        "effective_risk_percent": EFFECTIVE_RISK_PERCENT,
        "estimated_costs_percent": TOTAL_COST_PERCENT,
        "btc_volume": round(amount_toman / entry_price, 8),
        "status": "open",
        "is_paper": True,
        "profit_toman": 0.0,
        "profit_pct": 0.0,
        "profit_net_toman": 0.0,
        "profit_net_pct": 0.0,
        "gross_pnl": 0.0,
        "net_pnl": 0.0,
        "metadata": metadata,
    }
    if shadow_type:
        base["id"] = f"shadow_{uuid.uuid4().hex[:8]}"
        base["shadow_type"] = shadow_type
        base["reason"] = reason
        base["is_shadow"] = True
        base["decision_path"] = f"shadow_{shadow_type}"
    else:
        base["decision_path"] = "paper_executed"
    return base


def make_rejected_candidate(reason_code, reason_detail, side, signal_type,
                            entry_price, btc_change_6h, rsi, metadata,
                            open_count_at_time):
    """
    paper_trade32: ثبت candidate‌های rejected به‌عنوان shadow.
    اینا توسط monitor10 پردازش میشن و PnL نظری‌شون محاسبه میشه.
    prefix: rejected_
    """
    shadow_type = f"rejected_{reason_code}"
    amount = calculate_position_size(signal_type) or MAX_TRADE_TOMAN
    trade = make_trade(
        side=side, entry_price=entry_price, signal_type=signal_type,
        btc_change_6h=btc_change_6h, rsi=rsi,
        amount_toman=amount, metadata=metadata,
        shadow_type=shadow_type, reason=reason_detail,
    )
    trade["rejection_reason_code"] = reason_code
    trade["rejection_reason_detail"] = reason_detail
    trade["open_positions_at_rejection"] = open_count_at_time
    return trade


def get_today_paper_trades(trades):
    today = datetime.now().date().isoformat()
    return [t for t in trades if t.get("date") == today]


def can_trade_today(trades):
    return len(get_today_paper_trades(trades)) < MAX_DAILY_TRADES


async def main():
    if not acquire_lock():
        return
    try:
        now = datetime.now()

        print("=== GLOBAL NEWS ===")
        news_titles, feed_counts = get_all_news()
        news_sentiment = analyze_sentiment(news_titles)
        print(f"GLOBAL: {news_sentiment['sentiment']} (pos={news_sentiment['pos']}, neg={news_sentiment['neg']})")
        save_news_history(news_sentiment, feed_counts, news_titles, now)

        print("\n=== IRAN NEWS ===")
        iran_impact = get_iran_news_impact()
        print(f"IRAN: sentiment={iran_impact['sentiment']}, count={iran_impact['iran_count']}, "
              f"up={iran_impact['up']}, down={iran_impact['down']}, fx={iran_impact['fx_count']} "
              f"(source={iran_impact.get('source')})")

        print("\n=== PRICES ===")
        wallex = get_wallex_prices()
        if not wallex:
            print("CANNOT GET WALLEX - EXIT")
            return
        btc_tmn = wallex["btc"]["last"]

        btc_usdt = get_btc_usdt()
        nobitex = await get_nobitex_price()
        aban = get_aban_price()

        save_price_comparison(wallex, nobitex, aban, btc_usdt, now)

        print("\n=== DOLLAR HISTORY (paper_trade32) ===")
        dollar_data = get_dollar_change_and_update_history(wallex, now)
        print(f"  USD/TMN last: {dollar_data.get('dollar_last')}")
        print(f"  USD 6h change: {dollar_data.get('dollar_6h_change_pct')}%")
        print(f"  USD 24h change: {dollar_data.get('dollar_24h_change_pct')}%")
        print(f"  history size: {dollar_data.get('dollar_history_size')}")

        btc_data, btc_sha = load_from_github(BTC_HISTORY_FILE)
        btc_history = [(datetime.fromisoformat(t), p) for t, p in btc_data] if btc_data else []
        print(f"\nBTC_HISTORY LOADED: {len(btc_history)}")

        btc_change_6h = calculate_btc_change(btc_history, btc_tmn, now, BTC_LOOKBACK_SHORT)
        btc_change_24h = calculate_btc_change(btc_history, btc_tmn, now, BTC_LOOKBACK_LONG)
        print(f"BTC_CHANGE_6H: {btc_change_6h:+.2f}%")
        print(f"BTC_CHANGE_24H: {btc_change_24h:+.2f}%")

        if not btc_history or btc_history[-1][1] != btc_tmn:
            btc_history.append((now, btc_tmn))
            btc_history[:] = [(t, p) for t, p in btc_history if now - t < timedelta(hours=48)]
            save_to_github(BTC_HISTORY_FILE, [(t.isoformat(), p) for t, p in btc_history], btc_sha)
            print("BTC_HISTORY UPDATED")

        print("\n=== RSI (Wallex OHLC — primary) ===")
        rsi, rsi_source, rsi_report = get_rsi_from_wallex_ohlc(hours=WALLEX_OHLC_HOURS)

        rsi_valid, rsi_validity_status, rsi_coverage = compute_rsi_validity(
            rsi, rsi_source, rsi_report
        )
        print(f"  [RSI-VALIDITY] source={rsi_source} | status={rsi_validity_status} | "
              f"valid={rsi_valid} | coverage={rsi_coverage}%")

        print("\n=== RSI (btc_history — legacy, comparison only) ===")
        legacy_rsi, legacy_source, legacy_report = get_legacy_rsi_from_btc_history(btc_history)
        if legacy_rsi is not None:
            print(f"  [RSI-LEGACY] value={legacy_rsi} source={legacy_source} "
                  f"coverage={legacy_report.get('coverage_pct', 0)}%")
        else:
            print(f"  [RSI-LEGACY] unavailable")

        print("\n=== METADATA EXTRAS (paper_trade32) ===")
        candles_1m = get_wallex_ohlc_1m(hours=WALLEX_OHLC_HOURS)
        buckets_15m = []
        if candles_1m:
            buckets_15m, _ = resample_1m_to_15m_ohlcv(candles_1m)
        extras = compute_metadata_extras(buckets_15m, wallex, now)
        extras["dollar_last"] = dollar_data.get("dollar_last")
        extras["dollar_6h_change_pct"] = dollar_data.get("dollar_6h_change_pct")
        extras["dollar_24h_change_pct"] = dollar_data.get("dollar_24h_change_pct")
        print(f"  volume_15m:     {extras.get('volume_current_15m')}")
        print(f"  volume_ratio:   {extras.get('volume_ratio')}")
        print(f"  ema_state:      {extras.get('ema_state')}")

        paper_data, _ = load_from_github(PAPER_TRADES_FILE)
        paper_trades_list = paper_data if paper_data else []
        open_count = count_open_positions(paper_trades_list)
        print(f"\nPAPER TRADES: {len(paper_trades_list)} total, {open_count} open")

        shadow_data, _ = load_from_github(SHADOW_TRADES_FILE)
        shadow_list = shadow_data if shadow_data else []
        print(f"SHADOW TRADES: {len(shadow_list)} total")

        side, signal_type = classify_signal_btc(
            btc_change_6h, btc_change_24h, rsi, rsi_valid=rsi_valid
        )
        print(f"\nSIGNAL: {side} ({signal_type})")

        metadata = build_metadata(
            wallex, news_sentiment, iran_impact,
            rsi, rsi_source, rsi_report, rsi_valid, rsi_validity_status,
            legacy_rsi, legacy_source, legacy_report,
            extras,
        )

        shadow_changed = False

        # CONFLICT case
        if side == "CONFLICT":
            entry_ask = wallex["btc"]["ask"]
            entry_bid = wallex["btc"]["bid"]
            rej = make_rejected_candidate(
                reason_code="conflict", reason_detail="BUY and SELL simultaneously",
                side="sell", signal_type="CONFLICT",
                entry_price=entry_bid, btc_change_6h=btc_change_6h, rsi=rsi,
                metadata=metadata, open_count_at_time=open_count,
            )
            shadow_list.append(rej)
            shadow_changed = True
            print(f"REJECTED (conflict) LOGGED as shadow")

        # TOP shadow — baseline + experiment
        if side and side != "CONFLICT" and signal_type == "TOP":
            entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
            shadow_amount = calculate_position_size(signal_type) or MAX_TRADE_TOMAN

            shadow_trade = make_trade(
                side=side, entry_price=entry_price, signal_type=signal_type,
                btc_change_6h=btc_change_6h, rsi=rsi,
                amount_toman=shadow_amount, metadata=metadata,
                shadow_type="top_only", reason="TOP signal shadow (baseline)",
            )
            shadow_list.append(shadow_trade)
            shadow_changed = True
            print(f"SHADOW (top_only) ADDED")

            if TOP_TREND_FILTER_ENABLED and btc_change_6h < TOP_TREND_CHG6H_THRESHOLD:
                trend_filtered = make_trade(
                    side=side, entry_price=entry_price, signal_type=signal_type,
                    btc_change_6h=btc_change_6h, rsi=rsi,
                    amount_toman=shadow_amount, metadata=metadata,
                    shadow_type="top_trend_filtered",
                    reason=f"TOP + chg6h<{TOP_TREND_CHG6H_THRESHOLD}",
                )
                shadow_list.append(trend_filtered)
                shadow_changed = True
                print(f"SHADOW (top_trend_filtered) ADDED | chg6h={btc_change_6h:+.2f}%")
            else:
                print(f"SHADOW (top_trend_filtered) SKIPPED | chg6h={btc_change_6h:+.2f}%")

        iran_warning_text = ""
        if side and side != "CONFLICT":
            warned, warn_reason = apply_iran_warning(side, iran_impact)
            if warned:
                print(f"⚠️ {warn_reason}")
                iran_warning_text = f"\n⚠️ هشدار اخبار ایران:\n{warn_reason}\n"

        # VETO case
        if side and side != "CONFLICT":
            vetoed, veto_reason = apply_news_veto(side, news_sentiment)
            if vetoed:
                print(f"🚫 {veto_reason}")
                entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                shadow_amount = calculate_position_size(signal_type) or MAX_TRADE_TOMAN
                shadow_trade = make_trade(
                    side=side, entry_price=entry_price, signal_type=signal_type,
                    btc_change_6h=btc_change_6h, rsi=rsi,
                    amount_toman=shadow_amount, metadata=metadata,
                    shadow_type="veto", reason=veto_reason,
                )
                shadow_list.append(shadow_trade)
                shadow_changed = True

                msg = (
                    f"🚫 Global News VETO\n\n"
                    f"📊 سیگنال: {side.upper()} ({signal_type})\n"
                    f"📰 اخبار جهانی: {news_sentiment['sentiment']} "
                    f"(+{news_sentiment['pos']}/-{news_sentiment['neg']})\n"
                    f"⚠️ دلیل: {veto_reason}\n"
                    f"👻 Shadow ثبت شد"
                )
                await bot.send_message(CHAT_ID, msg)
                side = None

        # === REJECTED CANDIDATE LOGGING (paper_trade32) ===
        if side and side != "CONFLICT":
            can_open, reason = can_open_new_position(paper_trades_list, side)

            if not can_open:
                print(f"SKIP: {reason}")
                # ثبت به‌عنوان rejected candidate
                entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                rej = make_rejected_candidate(
                    reason_code=reason.lower(), reason_detail=reason,
                    side=side, signal_type=signal_type,
                    entry_price=entry_price, btc_change_6h=btc_change_6h, rsi=rsi,
                    metadata=metadata, open_count_at_time=open_count,
                )
                shadow_list.append(rej)
                shadow_changed = True
                print(f"REJECTED CANDIDATE LOGGED as shadow_{rej['shadow_type']}")

            elif not can_trade_today(paper_trades_list):
                print("DAILY LIMIT")
                entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                rej = make_rejected_candidate(
                    reason_code="daily_limit", reason_detail=f"MAX_DAILY_TRADES={MAX_DAILY_TRADES}",
                    side=side, signal_type=signal_type,
                    entry_price=entry_price, btc_change_6h=btc_change_6h, rsi=rsi,
                    metadata=metadata, open_count_at_time=open_count,
                )
                shadow_list.append(rej)
                shadow_changed = True
                print(f"REJECTED CANDIDATE LOGGED as shadow_daily_limit")

            else:
                amount_toman = calculate_position_size(signal_type)
                if amount_toman is None:
                    print("SIGNAL TOO WEAK")
                    entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                    rej = make_rejected_candidate(
                        reason_code="signal_too_weak", reason_detail="position_size below MIN_TRADE",
                        side=side, signal_type=signal_type,
                        entry_price=entry_price, btc_change_6h=btc_change_6h, rsi=rsi,
                        metadata=metadata, open_count_at_time=open_count,
                    )
                    shadow_list.append(rej)
                    shadow_changed = True
                    print(f"REJECTED CANDIDATE LOGGED as shadow_signal_too_weak")

                else:
                    entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                    trade = make_trade(
                        side=side, entry_price=entry_price, signal_type=signal_type,
                        btc_change_6h=btc_change_6h, rsi=rsi,
                        amount_toman=amount_toman, metadata=metadata,
                    )
                    paper_trades_list.append(trade)
                    save_to_github(PAPER_TRADES_FILE, paper_trades_list)

                    emoji = "🟢" if side == "buy" else "🔴"
                    type_fa = {
                        "VERY_STRONG": "خیلی قوی", "STRONG": "قوی", "MEDIUM": "متوسط",
                        "MOMENTUM": "مومنتوم", "DIP": "کف‌گیری", "TOP": "سقف‌گیری"
                    }.get(signal_type, signal_type)

                    price_label = "ask" if side == "buy" else "bid"
                    rsi_info = f"{rsi} ({rsi_source})"

                    rsi_valid_line = ""
                    if not rsi_valid:
                        rsi_valid_line = f"\n⚠️ RSI نامعتبر (status={rsi_validity_status}, coverage={rsi_coverage}%)"

                    legacy_line = ""
                    if legacy_rsi is not None:
                        legacy_line = f"\n📊 RSI قدیم: {legacy_rsi} ({legacy_report.get('coverage_pct', 0)}%)"

                    msg = (
                        f"{emoji} Paper Trade: {side.upper()} ({type_fa})\n\n"
                        f"🏦 والکس | last: {_fmt(btc_tmn)}\n"
                        f"💰 entry ({price_label}): {_fmt(entry_price)}\n"
                        f"🛑 SL: {_fmt(trade['stop_price'])}\n"
                        f"🎯 TP: {_fmt(trade['target_price'])}\n"
                        f"💵 مبلغ: {_fmt(amount_toman)}\n"
                        f"📈 تغییر ۶h: {btc_change_6h:+.2f}%\n"
                        f"📊 RSI: {rsi_info}{rsi_valid_line}{legacy_line}\n"
                        f"📰 اخبار جهانی: {news_sentiment['sentiment']} (+{news_sentiment['pos']}/-{news_sentiment['neg']})\n"
                        f"🇮🇷 اخبار ایران: {iran_impact['sentiment']} (⬆️{iran_impact['up']}/⬇️{iran_impact['down']})"
                        f"{iran_warning_text}\n"
                        f"{WARNING_MSG}"
                    )
                    await bot.send_message(CHAT_ID, msg)
                    print(f"TRADE EXECUTED: {side} ({signal_type})")
        elif side != "CONFLICT":
            print("NO SIGNAL")

        # RSI-invalid case: log candidate if signal would have fired
        if not rsi_valid and rsi is not None:
            # فقط اگر RSI معتبر بود، candidate رو ثبت کن برای مقایسه
            rsi_virtual = rsi
            side_v, sig_v = classify_signal_btc(btc_change_6h, btc_change_24h, rsi_virtual, rsi_valid=True)
            if side_v and side_v != "CONFLICT":
                entry_price = wallex["btc"]["ask"] if side_v == "buy" else wallex["btc"]["bid"]
                rej = make_rejected_candidate(
                    reason_code="rsi_invalid", reason_detail=f"coverage={rsi_coverage}% status={rsi_validity_status}",
                    side=side_v, signal_type=sig_v or "UNKNOWN",
                    entry_price=entry_price, btc_change_6h=btc_change_6h, rsi=rsi,
                    metadata=metadata, open_count_at_time=open_count,
                )
                shadow_list.append(rej)
                shadow_changed = True
                print(f"REJECTED CANDIDATE (rsi_invalid) LOGGED: {side_v} {sig_v}")

        # Shadow trimming
        if len(shadow_list) > MAX_SHADOW_TRADES:
            closed_old = [s for s in shadow_list if s.get("status") == "closed"]
            open_old = [s for s in shadow_list if s.get("status") == "open"]
            n_closed_keep = max(0, MAX_SHADOW_TRADES - len(open_old))
            closed_old = closed_old[-n_closed_keep:] if n_closed_keep else []
            shadow_list = closed_old + open_old
            shadow_changed = True

        if shadow_changed:
            save_to_github(SHADOW_TRADES_FILE, shadow_list)
            print("SHADOW_SAVED")

    finally:
        release_lock()


asyncio.run(main())
