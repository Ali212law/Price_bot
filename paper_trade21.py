import asyncio
import websockets
import json
import os
import base64
import time
import uuid
import random
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
LOCK_FILE = "lock.json"

CODE_VERSION = "paper_trade21"

LOCK_MAX_AGE_SECONDS = 720

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

IRR_TO_TOMAN = 10

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
MAX_SHADOW_TRADES = 200  # حداکثر shadow در فایل

STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3.0
EFFECTIVE_RISK_PERCENT = STOP_LOSS_PERCENT + TOTAL_COST_PERCENT

BTC_LOOKBACK_SHORT = 6
BTC_LOOKBACK_LONG = 24
MAX_DATA_AGE_SECONDS = 300

RSI_RESAMPLE_MINUTES = 15
RSI_PERIOD = 14
MIN_RESAMPLED_RECORDS = 20

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

NOBITEX_WS_URL = "wss://ws.nobitex.ir/connection/websocket"
WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"

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


def calculate_position_size(signal_type):
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    size = risk_toman / (EFFECTIVE_RISK_PERCENT / 100)
    size = min(size, MAX_TRADE_TOMAN)
    if size < MIN_TRADE_TOMAN:
        return None
    return round(size, 0)


def request_with_retry(url, headers=None, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
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


# ═══════════════════════════════════════════
# RSI Resample + Data Quality Report
# ═══════════════════════════════════════════

def resample_history(btc_history, interval_minutes=RSI_RESAMPLE_MINUTES):
    """تبدیل به کندل‌های هم‌فاصله + گزارش کیفیت"""
    if not btc_history or len(btc_history) < 2:
        return btc_history, {}

    sorted_hist = sorted(btc_history, key=lambda x: x[0])

    resampled = []
    current_bucket = None
    bucket_last_price = None
    bucket_record_count = 0
    buckets_info = {}  # bucket_start -> count

    for t, p in sorted_hist:
        bucket_minute = (t.minute // interval_minutes) * interval_minutes
        bucket_start = t.replace(minute=bucket_minute, second=0, microsecond=0)

        if current_bucket is None:
            current_bucket = bucket_start
            bucket_last_price = p
            bucket_record_count = 1
        elif bucket_start == current_bucket:
            bucket_last_price = p
            bucket_record_count += 1
        else:
            resampled.append((current_bucket, bucket_last_price))
            buckets_info[current_bucket] = bucket_record_count
            current_bucket = bucket_start
            bucket_last_price = p
            bucket_record_count = 1

    if bucket_last_price is not None:
        resampled.append((current_bucket, bucket_last_price))
        buckets_info[current_bucket] = bucket_record_count

    # محاسبه‌ی کندل‌های مورد انتظار و خالی
    first_ts = sorted_hist[0][0]
    last_ts = sorted_hist[-1][0]
    total_minutes = (last_ts - first_ts).total_seconds() / 60
    expected_candles = int(total_minutes / interval_minutes) + 1
    empty_candles = expected_candles - len(resampled)
    duplicate_records = sum(1 for c in buckets_info.values() if c > 1)
    max_records_in_bucket = max(buckets_info.values()) if buckets_info else 0

    report = {
        "total_records": len(btc_history),
        "resampled_candles": len(resampled),
        "expected_candles": expected_candles,
        "empty_candles": empty_candles,
        "coverage_pct": round(len(resampled) / expected_candles * 100, 1) if expected_candles else 0,
        "buckets_with_duplicates": duplicate_records,
        "max_records_in_bucket": max_records_in_bucket,
        "first_ts": first_ts.isoformat(),
        "last_ts": last_ts.isoformat(),
    }
    return resampled, report


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


def get_rsi_with_report(btc_history):
    """برمی‌گردونه: (rsi, source, report)"""
    if not btc_history:
        return None, "none", {}

    resampled, report = resample_history(btc_history, RSI_RESAMPLE_MINUTES)
    print(f"  [RSI] Original: {report.get('total_records')} | Resampled: {report.get('resampled_candles')}")
    print(f"  [RSI] Expected: {report.get('expected_candles')} | Empty: {report.get('empty_candles')} | Coverage: {report.get('coverage_pct')}%")
    print(f"  [RSI] Duplicates: {report.get('buckets_with_duplicates')} buckets | Max in bucket: {report.get('max_records_in_bucket')}")

    if len(resampled) < MIN_RESAMPLED_RECORDS:
        print(f"  [RSI] Not enough ({len(resampled)} < {MIN_RESAMPLED_RECORDS})")
        return None, "none", report

    prices = [p for _, p in resampled]
    rsi = calculate_rsi(prices, RSI_PERIOD)
    if rsi is None:
        return None, "none", report

    print(f"  [RSI] Calculated: {rsi}")
    return rsi, "resample", report


# ═══════════════════════════════════════════
# News
# ═══════════════════════════════════════════

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
    print(f"NEWS: {len(all_titles)} titles")
    return all_titles, feed_counts


def analyze_sentiment(titles):
    if not titles:
        return {"sentiment": "neutral", "pos": 0, "neg": 0, "matched": []}

    pos_count = 0
    neg_count = 0
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

    if pos_count > neg_count:
        sentiment = "positive"
    elif neg_count > pos_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "pos": pos_count,
        "neg": neg_count,
        "matched": matched[:10],
    }


def apply_news_veto(side, sentiment_data):
    if side is None:
        return False, "no signal"

    sentiment = sentiment_data["sentiment"]
    pos = sentiment_data["pos"]
    neg = sentiment_data["neg"]

    if side == "buy" and sentiment == "negative":
        if neg > pos * VETO_MULTIPLIER:
            return True, f"NEWS VETO BUY (neg={neg} > pos×{VETO_MULTIPLIER})"

    if side == "sell" and sentiment == "positive":
        if pos > neg * VETO_MULTIPLIER:
            return True, f"NEWS VETO SELL (pos={pos} > neg×{VETO_MULTIPLIER})"

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
            "matched": sentiment_data["matched"],
        }
        data, sha = load_from_github(NEWS_HISTORY_FILE)
        history = data if data else []
        history.append(entry)
        cutoff = (now - timedelta(days=7)).isoformat()
        history = [h for h in history if h.get("time", "") >= cutoff]
        history = history[-500:]
        save_to_github(NEWS_HISTORY_FILE, history, sha)
        print(f"NEWS_HISTORY SAVED")
    except Exception as e:
        print(f"NEWS_HISTORY ERROR: {e}")


def save_veto_log(side, signal_type, reason, sentiment_data, now):
    try:
        data, sha = load_from_github(VETO_LOG_FILE)
        logs = data if data else []
        logs.append({
            "time": now.isoformat(),
            "side": side,
            "signal_type": signal_type,
            "reason": reason,
            "sentiment": sentiment_data["sentiment"],
            "pos": sentiment_data["pos"],
            "neg": sentiment_data["neg"],
        })
        logs = logs[-200:]
        save_to_github(VETO_LOG_FILE, logs, sha)
    except Exception as e:
        print(f"VETO LOG ERROR: {e}")


# ═══════════════════════════════════════════
# Exchange prices
# ═══════════════════════════════════════════

def get_wallex_price():
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
        stats = btc.get("stats", {})
        if not stats:
            return None
        last_price = float(stats.get("lastPrice", 0))
        bid = float(stats.get("bidPrice", 0))
        ask = float(stats.get("askPrice", 0))
        data_age = (fetch_end - fetch_start).total_seconds()
        print(f"WALLEX: last={last_price:,.0f} | bid={bid:,.0f} | ask={ask:,.0f}")
        if data_age > MAX_DATA_AGE_SECONDS:
            return None
        return {
            "last": last_price, "bid": bid, "ask": ask,
            "spread_pct": ((ask - bid) / bid * 100) if bid else 0,
            "fetch_end": fetch_end.isoformat(),
            "data_age_seconds": round(data_age, 2),
        }
    except Exception as e:
        print(f"WALLEX ERROR: {e}")
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
        return {"buy": buy, "sell": sell, "mid": mid,
                "spread_pct": ((buy - sell) / sell * 100) if sell else 0}
    except Exception as e:
        print(f"ABAN ERROR: {e}")
        return None


def save_price_comparison(wallex, nobitex, aban, now):
    if not wallex:
        return
    try:
        entry = {
            "time": now.isoformat(),
            "wallex_last": wallex["last"],
            "wallex_bid": wallex["bid"],
            "wallex_ask": wallex["ask"],
            "wallex_spread_pct": round(wallex["spread_pct"], 4),
        }
        if nobitex:
            entry["nobitex_last"] = nobitex["last"]
            entry["nobitex_bid"] = nobitex["bid"]
            entry["nobitex_ask"] = nobitex["ask"]
            diff_wn = nobitex["bid"] - wallex["ask"]
            entry["wallex_to_nobitex"] = round(diff_wn, 0)
            entry["wallex_to_nobitex_pct"] = round((diff_wn / wallex["ask"]) * 100, 4)
        if aban:
            entry["aban_buy"] = aban["buy"]
            entry["aban_sell"] = aban["sell"]
            entry["aban_mid"] = aban["mid"]
            diff_wa = aban["sell"] - wallex["ask"]
            entry["wallex_to_aban"] = round(diff_wa, 0)
            entry["wallex_to_aban_pct"] = round((diff_wa / wallex["ask"]) * 100, 4)
        data, sha = load_from_github(PRICE_COMPARISON_FILE)
        history = data if data else []
        history.append(entry)
        cutoff = (now - timedelta(days=7)).isoformat()
        history = [h for h in history if h.get("time", "") >= cutoff]
        save_to_github(PRICE_COMPARISON_FILE, history, sha)
        print("COMPARISON SAVED")
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
        save_to_github(LOCK_FILE, new_lock, lock_sha)
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


def get_btc_history_coingecko(days=14):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
        r = request_with_retry(url)
        if not r:
            return []
        data = r.json()
        return [p[1] for p in data["prices"]]
    except Exception as e:
        print(f"BTC HISTORY ERROR: {e}")
        return []


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


def classify_signal_btc(btc_change_6h, btc_change_24h, rsi):
    if rsi is None:
        rsi = 50

    buy_signals = []
    sell_signals = []

    if rsi < RSI_OVERSOLD and btc_change_6h >= THRESHOLD_VERY_STRONG:
        buy_signals.append("VERY_STRONG")
    if rsi < RSI_LOW and btc_change_6h >= THRESHOLD_STRONG:
        buy_signals.append("STRONG")
    if rsi < RSI_MILD_LOW and btc_change_6h >= THRESHOLD_MEDIUM:
        buy_signals.append("MEDIUM")
    if btc_change_6h >= THRESHOLD_MOMENTUM:
        buy_signals.append("MOMENTUM")
    if rsi < RSI_OVERSOLD:
        buy_signals.append("DIP")

    if rsi > RSI_OVERBOUGHT and btc_change_6h <= -THRESHOLD_VERY_STRONG:
        sell_signals.append("VERY_STRONG")
    if rsi > RSI_HIGH and btc_change_6h <= -THRESHOLD_STRONG:
        sell_signals.append("STRONG")
    if rsi > RSI_MILD_HIGH and btc_change_6h <= -THRESHOLD_MEDIUM:
        sell_signals.append("MEDIUM")
    if btc_change_6h <= -THRESHOLD_MOMENTUM:
        sell_signals.append("MOMENTUM")
    if rsi > RSI_OVERBOUGHT:
        sell_signals.append("TOP")

    if buy_signals and sell_signals:
        print(f"CONFLICT! → NO TRADE")
        return None, None

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
        return False, f"ALREADY HAVE OPEN {side.upper()}"
    open_count = count_open_positions(trades)
    if open_count >= MAX_OPEN_POSITIONS:
        return False, f"MAX {MAX_OPEN_POSITIONS} POSITIONS"
    return True, "OK"


def build_metadata(wallex_data, news_sentiment, rsi, rsi_source, rsi_report):
    return {
        "code_version": CODE_VERSION,
        "run_time": datetime.now().isoformat(),
        "rsi_source": rsi_source,
        "rsi_value": rsi,
        "rsi_report": rsi_report,
        "news_sentiment": news_sentiment["sentiment"],
        "news_pos": news_sentiment["pos"],
        "news_neg": news_sentiment["neg"],
        "wallex_last": wallex_data.get("last"),
        "wallex_bid": wallex_data.get("bid"),
        "wallex_ask": wallex_data.get("ask"),
        "data_age_seconds": wallex_data.get("data_age_seconds"),
    }


def make_trade(side, entry_price, signal_type, btc_change_6h, rsi,
               amount_toman, metadata, shadow_type=None, reason=None):
    """ساختار مشترک برای paper و shadow"""
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
        "metadata": metadata,
    }

    if shadow_type:
        base["id"] = f"shadow_{uuid.uuid4().hex[:8]}"
        base["shadow_type"] = shadow_type  # "veto" or "top_only"
        base["reason"] = reason
        base["is_shadow"] = True

    return base


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

        # === News ===
        print("=== NEWS ===")
        news_titles, feed_counts = get_all_news()
        news_sentiment = analyze_sentiment(news_titles)
        print(f"NEWS: {news_sentiment['sentiment']} (pos={news_sentiment['pos']}, neg={news_sentiment['neg']})")
        save_news_history(news_sentiment, feed_counts, news_titles, now)

        # === Prices ===
        wallex = get_wallex_price()
        if not wallex:
            print("CANNOT GET WALLEX PRICE")
            return
        btc_for_signal = wallex["last"]

        nobitex = await get_nobitex_price()
        aban = get_aban_price()
        save_price_comparison(wallex, nobitex, aban, now)

        # === BTC History ===
        btc_data, btc_sha = load_from_github(BTC_HISTORY_FILE)
        btc_history = [(datetime.fromisoformat(t), p) for t, p in btc_data] if btc_data else []
        print(f"BTC_HISTORY LOADED: {len(btc_history)} records")

        btc_change_6h = calculate_btc_change(btc_history, btc_for_signal, now, BTC_LOOKBACK_SHORT)
        btc_change_24h = calculate_btc_change(btc_history, btc_for_signal, now, BTC_LOOKBACK_LONG)
        print(f"BTC_CHANGE_6H: {btc_change_6h:+.2f}%")
        print(f"BTC_CHANGE_24H: {btc_change_24h:+.2f}%")

        if not btc_history or btc_history[-1][1] != btc_for_signal:
            btc_history.append((now, btc_for_signal))
            btc_history[:] = [(t, p) for t, p in btc_history if now - t < timedelta(hours=48)]
            save_to_github(BTC_HISTORY_FILE, [(t.isoformat(), p) for t, p in btc_history], btc_sha)
            print("BTC_HISTORY UPDATED")

        # === RSI ===
        print("=== RSI ===")
        rsi, rsi_source, rsi_report = get_rsi_with_report(btc_history)

        if rsi is None:
            print("RSI: fallback to CoinGecko")
            prices = get_btc_history_coingecko(14)
            rsi = calculate_rsi(prices)
            rsi_source = "coingecko_fallback"
            print(f"RSI (fallback): {rsi}")

        # === Load Paper & Shadow ===
        paper_data, paper_sha = load_from_github(PAPER_TRADES_FILE)
        paper_trades_list = paper_data if paper_data else []
        open_count = count_open_positions(paper_trades_list)
        print(f"PAPER TRADES: {len(paper_trades_list)} total, {open_count} open")

        shadow_data, shadow_sha = load_from_github(SHADOW_TRADES_FILE)
        shadow_list = shadow_data if shadow_data else []
        shadow_open = count_open_positions(shadow_list)
        print(f"SHADOW TRADES: {len(shadow_list)} total, {shadow_open} open")

        # === Update Paper Trades (SL/TP) ===
        for t in paper_trades_list:
            if t.get("status") != "open":
                continue
            entry = t["entry_price"]
            side = t.get("side", "").lower()
            amount = t.get("amount_toman", 50000)

            if side == "buy":
                exit_price = wallex["bid"]
                change_pct = ((exit_price - entry) / entry) * 100
            else:
                exit_price = wallex["ask"]
                change_pct = ((entry - exit_price) / entry) * 100

            if change_pct <= -STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None

            if action:
                net_pct = change_pct - TOTAL_COST_PERCENT
                net_toman = (net_pct / 100) * amount
                t["status"] = "closed"
                t["exit_price"] = exit_price
                t["exit_price_toman"] = exit_price
                t["exit_price_irr"] = exit_price * IRR_TO_TOMAN
                t["exit_time"] = now.isoformat()
                t["exit_reason"] = action
                t["profit_pct"] = change_pct
                t["profit_toman"] = (change_pct / 100) * amount
                t["profit_net_toman"] = round(net_toman, 0)
                t["profit_net_pct"] = round(net_pct, 4)
                print(f"PAPER {action.upper()}: gross={change_pct:+.2f}% | net={net_pct:+.2f}%")

        # === Update Shadow Trades (SL/TP) ===
        for s in shadow_list:
            if s.get("status") != "open":
                continue
            entry = s["entry_price"]
            side = s.get("side", "").lower()
            amount = s.get("amount_toman", 50000)

            if side == "buy":
                exit_price = wallex["bid"]
                change_pct = ((exit_price - entry) / entry) * 100
            else:
                exit_price = wallex["ask"]
                change_pct = ((entry - exit_price) / entry) * 100

            if change_pct <= -STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None

            if action:
                net_pct = change_pct - TOTAL_COST_PERCENT
                net_toman = (net_pct / 100) * amount
                s["status"] = "closed"
                s["exit_price"] = exit_price
                s["exit_time"] = now.isoformat()
                s["exit_reason"] = action
                s["profit_pct"] = change_pct
                s["profit_toman"] = (change_pct / 100) * amount
                s["profit_net_toman"] = round(net_toman, 0)
                s["profit_net_pct"] = round(net_pct, 4)
                print(f"SHADOW {s.get('shadow_type', '?')} {action.upper()}: gross={change_pct:+.2f}%")

        # === Signal ===
        side, signal_type = classify_signal_btc(btc_change_6h, btc_change_24h, rsi)
        print(f"SIGNAL: {side} ({signal_type})")

        metadata = build_metadata(wallex, news_sentiment, rsi, rsi_source, rsi_report)

        # === Shadow for TOP ===
        if side and signal_type == "TOP":
            if side == "buy":
                shadow_entry = wallex["ask"]
            else:
                shadow_entry = wallex["bid"]

            shadow_amount = calculate_position_size(signal_type) or MAX_TRADE_TOMAN
            shadow_trade = make_trade(
                side=side, entry_price=shadow_entry, signal_type=signal_type,
                btc_change_6h=btc_change_6h, rsi=rsi,
                amount_toman=shadow_amount, metadata=metadata,
                shadow_type="top_only",
                reason="TOP signal shadow tracking",
            )
            shadow_list.append(shadow_trade)
            # حذف قدیمی‌ها
            if len(shadow_list) > MAX_SHADOW_TRADES:
                closed_old = [s for s in shadow_list if s.get("status") == "closed"]
                open_old = [s for s in shadow_list if s.get("status") == "open"]
                closed_old = closed_old[-(MAX_SHADOW_TRADES - len(open_old)):]
                shadow_list = closed_old + open_old
            save_to_github(SHADOW_TRADES_FILE, shadow_list, shadow_sha)
            print(f"SHADOW (top_only) ADDED: {side} {signal_type}")

        # === News Veto ===
        if side:
            vetoed, veto_reason = apply_news_veto(side, news_sentiment)
            if vetoed:
                print(f"🚫 {veto_reason}")

                # Shadow for veto
                if side == "buy":
                    shadow_entry = wallex["ask"]
                else:
                    shadow_entry = wallex["bid"]

                shadow_amount = calculate_position_size(signal_type) or MAX_TRADE_TOMAN
                shadow_trade = make_trade(
                    side=side, entry_price=shadow_entry, signal_type=signal_type,
                    btc_change_6h=btc_change_6h, rsi=rsi,
                    amount_toman=shadow_amount, metadata=metadata,
                    shadow_type="veto",
                    reason=veto_reason,
                )
                shadow_list.append(shadow_trade)
                if len(shadow_list) > MAX_SHADOW_TRADES:
                    closed_old = [s for s in shadow_list if s.get("status") == "closed"]
                    open_old = [s for s in shadow_list if s.get("status") == "open"]
                    closed_old = closed_old[-(MAX_SHADOW_TRADES - len(open_old)):]
                    shadow_list = closed_old + open_old
                save_to_github(SHADOW_TRADES_FILE, shadow_list, shadow_sha)

                save_veto_log(side, signal_type, veto_reason, news_sentiment, now)

                msg = (
                    f"🚫 Paper Trade VETO\n\n"
                    f"📊 سیگنال: {side.upper()} ({signal_type})\n"
                    f"📰 اخبار: {news_sentiment['sentiment']} "
                    f"(+{news_sentiment['pos']}/-{news_sentiment['neg']})\n"
                    f"⚠️ دلیل: {veto_reason}\n"
                    f"👻 Shadow trade ثبت شد"
                )
                await bot.send_message(CHAT_ID, msg)
                side = None

        # === Normal Paper Trade ===
        if side:
            can_open, reason = can_open_new_position(paper_trades_list, side)
            if not can_open:
                print(f"SKIP: {reason}")
            elif not can_trade_today(paper_trades_list):
                print("DAILY LIMIT")
            else:
                amount_toman = calculate_position_size(signal_type)
                if amount_toman is None:
                    print("SIGNAL TOO WEAK")
                else:
                    if side == "buy":
                        entry_price = wallex["ask"]
                    else:
                        entry_price = wallex["bid"]

                    trade = make_trade(
                        side=side, entry_price=entry_price, signal_type=signal_type,
                        btc_change_6h=btc_change_6h, rsi=rsi,
                        amount_toman=amount_toman, metadata=metadata,
                    )
                    paper_trades_list.append(trade)
                    save_to_github(PAPER_TRADES_FILE, paper_trades_list, paper_sha)

                    emoji = "🟢" if side == "buy" else "🔴"
                    type_fa = {
                        "VERY_STRONG": "خیلی قوی", "STRONG": "قوی", "MEDIUM": "متوسط",
                        "MOMENTUM": "مومنتوم", "DIP": "کف‌گیری", "TOP": "سقف‌گیری"
                    }.get(signal_type, signal_type)

                    price_label = "ask" if side == "buy" else "bid"
                    rsi_info = f"{rsi} ({rsi_source})"

                    msg = (
                        f"{emoji} Paper Trade: {side.upper()} ({type_fa})\n\n"
                        f"🏦 والکس | 📊 last: {_fmt(wallex['last'])}\n"
                        f"💰 entry ({price_label}): {_fmt(entry_price)}\n"
                        f"🛑 SL: {_fmt(trade.get('stop_price'))} ({STOP_LOSS_PERCENT}%)\n"
                        f"🎯 TP: {_fmt(trade.get('target_price'))} ({TAKE_PROFIT_PERCENT}%)\n"
                        f"💵 مبلغ: {_fmt(amount_toman)} | ⚠️ ریسک: {_fmt(trade['max_risk_toman'])}\n"
                        f"📉 هزینه: {TOTAL_COST_PERCENT}%\n"
                        f"📈 تغییر ۶h: {btc_change_6h:+.2f}%\n"
                        f"📊 RSI: {rsi_info}\n"
                        f"📰 اخبار: {news_sentiment['sentiment']} (+{news_sentiment['pos']}/-{news_sentiment['neg']})\n"
                        f"{WARNING_MSG}"
                    )
                    await bot.send_message(CHAT_ID, msg)
                    print(f"TRADE EXECUTED: {side} ({signal_type})")
        else:
            print(f"NO SIGNAL")

        # === Final Save (Shadow) ===
        save_to_github(SHADOW_TRADES_FILE, shadow_list, shadow_sha)
    finally:
        release_lock()


asyncio.run(main())
