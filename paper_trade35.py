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

# --- ISOLATION FILES ---
HISTORY_FILE = "dollar_history.json"  # shared
BTC_HISTORY_FILE = "btc_history.json" # shared
PAPER_TRADES_FILE = "paper_trades35.json"   # isolated
SHADOW_TRADES_FILE = "shadow_trades35.json" # isolated
PRICE_COMPARISON_FILE = "price_comparison.json" # shared
NEWS_HISTORY_FILE = "news_history.json" # shared
VETO_LOG_FILE = "veto_log.json" # shared
IRAN_NEWS_FILE = "iran_news_data.json" # shared
PRICE_COMPONENTS_FILE = "price_components.json" # shared
LOCK_FILE = "lock35.json"           # isolated
TIME_ANCHOR_FILE = "time_anchor35.json" # isolated

CODE_VERSION = "paper_trade35"

LOCK_MAX_AGE_SECONDS = 720

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

IRR_TO_TOMAN = 10
PRICE_UNIT_THRESHOLD = 100_000_000_000

# --- M2 PARAMETERS ---
MAX_RISK_TABLE = {
    "DIP": 700, # Only DIP is active
}
DEFAULT_MAX_RISK = 300

MAX_TRADE_TOMAN = 50000
MIN_TRADE_TOMAN = 5000
MAX_DAILY_TRADES = 5
MAX_OPEN_POSITIONS = 1
MAX_SHADOW_TRADES = 500

STOP_LOSS_PERCENT = 2.0
TAKE_PROFIT_PERCENT = 4.0
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

REGIME_BULL_THRESHOLD = 1.5
REGIME_BEAR_THRESHOLD = -1.5
REGIME_RANGE_THRESHOLD = 0.5

EMA_FAST_PERIOD = 9
EMA_SLOW_PERIOD = 21
VOLUME_LOOKBACK_BUCKETS = 96
DOLLAR_HISTORY_MAX_HOURS = 48
BTC_HISTORY_MAX_HOURS = 2160

NOBITEX_WS_URL = "wss://ws.nobitex.ir/connection/websocket"
WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"
WALLEX_USDT_SYMBOL = "USDTTMN"

BINANCE_API_URL = "https://api.binance.com"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

ABAN_IP = "185.143.234.130"
ABAN_HOST = "api.abantether.com"
ABAN_TICKER_URL = f"https://{ABAN_HOST}/api/v1/manager/otc/ticker"

SIGNAL_PRIORITY = ["DIP"]

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
WARNING_MSG = "⚠️ این Paper Trading (M2) است. معامله واقعی انجام نمی‌شود."

_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, *args, **kwargs):
    if host == ABAN_HOST:
        return _original_getaddrinfo(ABAN_IP, *args, **kwargs)
    return _original_getaddrinfo(host, *args, **kwargs)

socket.getaddrinfo = _patched_getaddrinfo


def _fmt(v):
    if v is None: return "N/A"
    try: return f"{float(v):,.0f}"
    except: return "N/A"


def normalize_price_unit(value):
    try:
        v = float(value)
        if v > PRICE_UNIT_THRESHOLD: return v / IRR_TO_TOMAN
        return v
    except: return value


def calculate_position_size(signal_type):
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    size = risk_toman / (EFFECTIVE_RISK_PERCENT / 100)
    size = min(size, MAX_TRADE_TOMAN)
    if size < MIN_TRADE_TOMAN: return None
    return round(size, 0)


def compute_rsi_validity(rsi, rsi_source, rsi_report):
    if rsi is None: return False, "no_rsi", 0.0
    if rsi_source == "wallex_failed": return False, "wallex_failed", 0.0
    coverage = float(rsi_report.get("coverage_pct", 0) or 0)
    if coverage >= RSI_COVERAGE_VALID_HIGH: return True, "high", coverage
    if coverage >= RSI_COVERAGE_VALID_LOW: return True, "medium_with_warning", coverage
    if coverage >= RSI_COVERAGE_MIN: return False, "low_invalid", coverage
    return False, "critical_invalid", coverage


def classify_regime(chg24h):
    if chg24h is None: return "unknown"
    if chg24h > REGIME_BULL_THRESHOLD: return "bull"
    if chg24h < REGIME_BEAR_THRESHOLD: return "bear"
    if abs(chg24h) < REGIME_RANGE_THRESHOLD: return "range"
    return "chop"


def compute_hypothetical_signal(btc_change_6h, btc_change_24h, rsi, rsi_valid):
    if rsi is None: return []
    side, sig = classify_signal_btc(btc_change_6h, btc_change_24h, rsi, rsi_valid)
    if side == "CONFLICT": return ["CONFLICT"]
    if not side: return []
    return [f"{side.upper()}:{sig}"]


def get_wallex_ohlc_1m(hours=WALLEX_OHLC_HOURS):
    try:
        now = int(time.time())
        from_ts = now - hours * 3600
        params = {"symbol": WALLEX_SYMBOL, "resolution": WALLEX_OHLC_RESOLUTION, "from": from_ts, "to": now}
        r = requests.get(WALLEX_OHLC_URL, params=params, timeout=20)
        if r.status_code != 200: return None
        data = r.json()
        if data.get("s") != "ok": return None

        t, o, h, l, c, v = data.get("t", []), data.get("o", []), data.get("h", []), data.get("l", []), data.get("c", []), data.get("v", [])
        n = min(len(t), len(o), len(h), len(l), len(c))
        if n < 100: return None

        sample_close = float(c[0]) if c else 0
        unit_divisor = IRR_TO_TOMAN if sample_close > PRICE_UNIT_THRESHOLD else 1

        candles = []
        for i in range(n):
            try:
                candles.append({"t": int(t[i]), "o": float(o[i])/unit_divisor, "h": float(h[i])/unit_divisor, "l": float(l[i])/unit_divisor, "c": float(c[i])/unit_divisor, "v": float(v[i]) if i < len(v) else 0.0})
            except: continue
        candles.sort(key=lambda x: x["t"])
        return candles
    except: return None


def resample_1m_to_15m_ohlcv(candles_1m):
    if not candles_1m: return [], {}
    buckets = {}
    for c in candles_1m:
        b_ts = (c["t"] // WALLEX_OHLC_BUCKET_SEC) * WALLEX_OHLC_BUCKET_SEC
        if b_ts not in buckets:
            buckets[b_ts] = {"t": b_ts, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"], "count": 1}
        else:
            b = buckets[b_ts]
            b["h"] = max(b["h"], c["h"]); b["l"] = min(b["l"], c["l"]); b["c"] = c["c"]; b["v"] += c["v"]; b["count"] += 1

    sorted_buckets = sorted(buckets.values(), key=lambda x: x["t"])
    expected = (sorted_buckets[-1]["t"] - sorted_buckets[0]["t"]) // WALLEX_OHLC_BUCKET_SEC + 1 if len(sorted_buckets) >= 2 else len(sorted_buckets)
    valid = [b for b in sorted_buckets if b["count"] >= WALLEX_OHLC_MIN_BUCKET_RECORDS]
    if valid and (int(time.time()) - valid[-1]["t"]) < WALLEX_OHLC_BUCKET_SEC: valid = valid[:-1]
    coverage = round(len(valid) / expected * 100, 1) if expected else 0.0
    report = {"source": "wallex_ohlc", "timeframe": "15m", "hours": WALLEX_OHLC_HOURS, "candles_1m": len(candles_1m), "buckets_total": len(sorted_buckets), "buckets_valid": len(valid), "buckets_expected": expected, "coverage_pct": coverage, "min_records_per_bucket": WALLEX_OHLC_MIN_BUCKET_RECORDS}
    return valid, report


def get_rsi_from_wallex_ohlc(hours=WALLEX_OHLC_HOURS):
    candles_1m = get_wallex_ohlc_1m(hours=hours)
    if not candles_1m: return None, "wallex_failed", {"source": "wallex_failed", "coverage_pct": 0.0}
    buckets_15m, report = resample_1m_to_15m_ohlcv(candles_1m)
    if len(buckets_15m) < MIN_RESAMPLED_RECORDS: return None, "wallex_insufficient", report
    prices = [b["c"] for b in buckets_15m]
    rsi = calculate_rsi(prices, RSI_PERIOD)
    return (rsi, "wallex_ohlc", report) if rsi else (None, "wallex_calc_failed", report)


def resample_history(btc_history, interval_minutes=RSI_RESAMPLE_MINUTES):
    if not btc_history or len(btc_history) < 2: return btc_history, {}
    sorted_hist = sorted(btc_history, key=lambda x: x[0])
    resampled = []
    current_bucket, bucket_last_price = None, None
    for t, p in sorted_hist:
        bucket_start = t.replace(minute=(t.minute // interval_minutes) * interval_minutes, second=0, microsecond=0)
        if current_bucket is None or bucket_start != current_bucket:
            if bucket_last_price is not None: resampled.append((current_bucket, bucket_last_price))
            current_bucket = bucket_start
        bucket_last_price = p
    if bucket_last_price is not None: resampled.append((current_bucket, bucket_last_price))
    expected = int(((sorted_hist[-1][0] - sorted_hist[0][0]).total_seconds() / 60) / interval_minutes) + 1
    coverage = round(len(resampled) / expected * 100, 1) if expected else 0
    return resampled, {"source": "btc_history_legacy", "resampled_candles": len(resampled), "expected_candles": expected, "coverage_pct": coverage}


def get_legacy_rsi_from_btc_history(btc_history):
    if not btc_history: return None, "none", {}
    resampled, report = resample_history(btc_history, RSI_RESAMPLE_MINUTES)
    if len(resampled) < MIN_RESAMPLED_RECORDS: return None, "none", report
    prices = [p for _, p in resampled]
    return calculate_rsi(prices, RSI_PERIOD), "btc_history_legacy", report


def calculate_rsi(prices, period=RSI_PERIOD):
    if not prices or len(prices) < period + 1: return None
    try:
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0: gains.append(change); losses.append(0)
            else: gains.append(0); losses.append(abs(change))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100
        return round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
    except: return None


def calculate_ema(prices, period):
    if not prices or len(prices) < period: return None
    try:
        k = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]: ema = p * k + ema * (1 - k)
        return round(ema, 2)
    except: return None


def get_dollar_change_and_update_history(wallex_data, now):
    result = {"dollar_6h_change_pct": None, "dollar_24h_change_pct": None, "dollar_last": None, "dollar_history_size": 0}
    try:
        usdt_last = normalize_price_unit(wallex_data["usdt"]["last"])
        if usdt_last <= 0: return result
        result["dollar_last"] = usdt_last
        data, sha = load_from_github(HISTORY_FILE)
        history = data if data and isinstance(data[0], list) else []
        history.append([now.isoformat(), usdt_last])
        cutoff = now - timedelta(hours=DOLLAR_HISTORY_MAX_HOURS)
        history = [h for h in history if datetime.fromisoformat(h[0]) >= cutoff]
        result["dollar_history_size"] = len(history)
        if len(history) >= 2:
            past_6h = [p for t_str, p in history if datetime.fromisoformat(t_str) <= now - timedelta(hours=6)]
            if past_6h and past_6h[0] > 0: result["dollar_6h_change_pct"] = round((usdt_last - past_6h[0]) / past_6h[0] * 100, 4)
            past_24h = [p for t_str, p in history if datetime.fromisoformat(t_str) <= now - timedelta(hours=24)]
            if past_24h and past_24h[0] > 0: result["dollar_24h_change_pct"] = round((usdt_last - past_24h[0]) / past_24h[0] * 100, 4)
        save_to_github(HISTORY_FILE, history, sha)
    except Exception as e: print(f"[DOLLAR] ERROR: {e}")
    return result


def compute_metadata_extras(candles_15m, wallex_data, now):
    extras = {"volume_current_15m": None, "volume_avg_15m_24h": None, "volume_ratio": None, "ema9_15m": None, "ema21_15m": None, "ema_state": None}
    try:
        if not candles_15m or len(candles_15m) < EMA_SLOW_PERIOD: return extras
        last_bucket = candles_15m[-1]
        extras["volume_current_15m"] = round(last_bucket["v"], 2)
        recent = candles_15m[-VOLUME_LOOKBACK_BUCKETS:]
        if recent:
            avg_vol = sum(b["v"] for b in recent) / len(recent)
            extras["volume_avg_15m_24h"] = round(avg_vol, 2)
            if avg_vol > 0: extras["volume_ratio"] = round(last_bucket["v"] / avg_vol, 3)
        closes = [b["c"] for b in candles_15m]
        ema9, ema21 = calculate_ema(closes, EMA_FAST_PERIOD), calculate_ema(closes, EMA_SLOW_PERIOD)
        extras["ema9_15m"], extras["ema21_15m"] = ema9, ema21
        if ema9 and ema21: extras["ema_state"] = "bull" if ema9 > ema21 else "bear"
    except: pass
    return extras


def get_iran_news_impact():
    data, _ = load_from_github(IRAN_NEWS_FILE)
    if not data: return {"iran_count": 0, "up": 0, "down": 0, "unclear": 0, "sentiment": "unclear", "fx_count": 0, "top_events": {}, "source": "no_data"}
    stats = data.get("stats", {}) if isinstance(data, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else data
    if stats and "by_btc_impact" in stats:
        up, down, unclear = stats["by_btc_impact"].get("up", 0), stats["by_btc_impact"].get("down", 0), stats["by_btc_impact"].get("unclear", 0)
        fx_count = stats.get("by_event", {}).get("fx", 0)
        iran_count = stats.get("recent_news_24h") or stats.get("unique_by_hash", 0)
        return {"iran_count": iran_count, "up": up, "down": down, "unclear": unclear, "sentiment": "bullish" if up > down*2 and up>=3 else ("bearish" if down > up*2 and down>=3 else "neutral"), "fx_count": fx_count, "top_events": stats.get("by_event", {}), "source": "stats"}
    return {"iran_count": len(items), "up": 0, "down": 0, "unclear": 0, "sentiment": "neutral", "fx_count": 0, "top_events": {}, "source": "computed"}


def apply_iran_warning(side, iran_impact):
    if side is None: return False, "no signal"
    if side == "sell" and iran_impact["sentiment"] == "bullish": return True, "IRAN WARNING: bullish Iran + SELL"
    if side == "buy" and iran_impact["sentiment"] == "bearish": return True, "IRAN WARNING: bearish Iran + BUY"
    return False, "OK"


def fetch_news_feed(name, url):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return []
        try:
            root = ET.fromstring(r.content)
            titles = [re.sub(r"<[^>]+>", "", item.find("title").text).strip() for item in root.findall(".//item")[:10] if item.find("title") is not None and item.find("title").text]
            return titles
        except:
            titles = re.findall(r"<title>(.*?)</title>", r.text, re.DOTALL)
            return [re.sub(r"<[^>]+>", "", t).strip() for t in titles if len(t.strip()) > 15][:10]
    except: return []


def get_all_news():
    all_titles, feed_counts = [], {}
    for name, url in NEWS_FEEDS.items():
        titles = fetch_news_feed(name, url)
        feed_counts[name] = len(titles)
        all_titles.extend(titles)
    return all_titles, feed_counts


def analyze_sentiment(titles):
    if not titles: return {"sentiment": "neutral", "pos": 0, "neg": 0, "matched": []}
    pos_count = neg_count = 0
    for title in titles:
        tl = title.lower()
        for w in POSITIVE_WORDS:
            if w in tl: pos_count += 1; break
        for w in NEGATIVE_WORDS:
            if w in tl: neg_count += 1; break
    return {"sentiment": "positive" if pos_count > neg_count else ("negative" if neg_count > pos_count else "neutral"), "pos": pos_count, "neg": neg_count, "matched": []}


def apply_news_veto(side, sentiment_data):
    if side is None: return False, "no signal"
    if side == "buy" and sentiment_data["sentiment"] == "negative" and sentiment_data["neg"] > sentiment_data["pos"] * VETO_MULTIPLIER: return True, "GLOBAL NEWS VETO BUY"
    if side == "sell" and sentiment_data["sentiment"] == "positive" and sentiment_data["pos"] > sentiment_data["neg"] * VETO_MULTIPLIER: return True, "GLOBAL NEWS VETO SELL"
    return False, "OK"


def save_news_history(sentiment_data, feed_counts, titles, now):
    try:
        entry = {"time": now.isoformat(), "sentiment": sentiment_data["sentiment"], "pos": sentiment_data["pos"], "neg": sentiment_data["neg"], "total_titles": len(titles), "feed_counts": feed_counts, "sample_titles": titles[:5]}
        data, sha = load_from_github(NEWS_HISTORY_FILE)
        history = data if data else []
        history.append(entry)
        history = [h for h in history if h.get("time", "") >= (now - timedelta(days=7)).isoformat()][-500:]
        save_to_github(NEWS_HISTORY_FILE, history, sha)
    except: pass


def get_wallex_prices():
    try:
        r = request_with_retry(f"{WALLEX_API_URL}/v1/markets", max_retries=3, timeout=15)
        if not r: return None
        symbols = r.json().get("result", {}).get("symbols", {})
        btc, usdt = symbols.get(WALLEX_SYMBOL, {}), symbols.get(WALLEX_USDT_SYMBOL, {})
        btc_stats, usdt_stats = btc.get("stats", {}), usdt.get("stats", {})
        if not btc_stats: return None
        def parse(s): 
            if not s: return 0.0
            v = float(s.get("lastPrice", 0))
            return v / IRR_TO_TOMAN if v > PRICE_UNIT_THRESHOLD else v
        btc_last = parse(btc_stats); usdt_last = parse(usdt_stats)
        return {"btc": {"last": btc_last, "bid": parse(btc_stats.get("bidPrice")), "ask": parse(btc_stats.get("askPrice"))}, "usdt": {"last": usdt_last}}
    except: return None


def get_btc_usdt():
    try:
        r = requests.get(f"{BINANCE_API_URL}/api/v3/ticker/bookTicker", params={"symbol": "BTCUSDT"}, timeout=10)
        if r.status_code == 200:
            d = r.json(); mid = (float(d["bidPrice"]) + float(d["askPrice"])) / 2
            return {"last": mid, "source": "binance"}
    except: pass
    return None


async def get_nobitex_price(max_attempts=3):
    return None # Disabled for speed/simplicity in M2 test

def get_aban_price():
    if not ABAN_API_KEY: return None
    try:
        r = requests.get(ABAN_TICKER_URL, headers={"Authorization": ABAN_API_KEY}, timeout=15)
        if r.status_code == 200:
            btc = r.json().get("data", {}).get("markets", {}).get("BTCIRT", {})
            return {"buy": float(btc.get("buy_price", 0)), "sell": float(btc.get("sell_price", 0)), "mid": (float(btc.get("buy_price", 0)) + float(btc.get("sell_price", 0))) / 2}
    except: pass
    return None


def save_price_comparison(wallex, nobitex, aban, btc_usdt, now):
    pass # Not critical for M2 test

def load_from_github(filename):
    try:
        r = request_with_retry(f"https://api.github.com/repos/{GH_REPO}/contents/{filename}", headers={"Authorization": f"token {GH_TOKEN}"})
        if r and r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return None, None
    except: return None, None


def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        payload = {"message": f"Update {filename}", "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")}
        if sha: payload["sha"] = sha
        r = put_with_retry(f"https://api.github.com/repos/{GH_REPO}/contents/{filename}", {"Authorization": f"token {GH_TOKEN}"}, payload)
        return bool(r and r.status_code in [200, 201])
    except: return False


def request_with_retry(url, headers=None, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in (200, 404): return r
        except: pass
        if attempt < max_retries - 1: time.sleep(3 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]: return r
        except: pass
        if attempt < max_retries - 1: time.sleep(3 ** attempt)
    return None


def acquire_lock():
    try:
        lock_data, lock_sha = load_from_github(LOCK_FILE)
        if lock_data and (datetime.now() - datetime.fromisoformat(lock_data.get("time", "2000-01-01"))).total_seconds() < LOCK_MAX_AGE_SECONDS:
            print(f"LOCK EXISTS - SKIP"); return False
        new_lock = {"time": datetime.now().isoformat(), "id": str(uuid.uuid4())}
        if not save_to_github(LOCK_FILE, new_lock, lock_sha): return False
        print("LOCK ACQUIRED"); return True
    except: return False


def release_lock():
    try:
        _, sha = load_from_github(LOCK_FILE)
        if sha: requests.delete(f"https://api.github.com/repos/{GH_REPO}/contents/{LOCK_FILE}", headers={"Authorization": f"token {GH_TOKEN}"}, json={"message": "Release", "sha": sha}, timeout=30)
    except: pass


def calculate_btc_change(btc_history, current_price, now, lookback_hours):
    if not btc_history or current_price is None: return 0.0
    recent = [(t, p) for t, p in btc_history if t >= now - timedelta(hours=lookback_hours)]
    if len(recent) >= 1:
        avg_old = sum(p for _, p in recent) / len(recent)
        return ((current_price - avg_old) / avg_old) * 100
    return 0.0


def calculate_btc_change_oldest(btc_history, current_price, now, lookback_hours):
    if not btc_history or current_price is None: return 0.0
    recent = [(t, p) for t, p in btc_history if t >= now - timedelta(hours=lookback_hours)]
    if len(recent) >= 2:
        oldest = min(recent, key=lambda x: x[0])[1]
        if oldest > 0: return ((current_price - oldest) / oldest) * 100
    return 0.0


# --- M2 STRATEGY: ONLY DIP ---
def classify_signal_btc(btc_change_6h, btc_change_24h, rsi, rsi_valid=True):
    if rsi is None or not rsi_valid:
        return None, None
    
    # Only DIP is allowed in Paper 35
    if rsi < RSI_OVERSOLD:
        return "buy", "DIP"
        
    return None, None


def has_open_position_in_direction(trades, side):
    return any(t.get("status") == "open" and t.get("side", "").lower() == side.lower() for t in trades)


def count_open_positions(trades):
    return len([t for t in trades if t.get("status") == "open"])


def can_open_new_position(trades, side):
    if has_open_position_in_direction(trades, side.lower()): return False, f"ALREADY_OPEN_{side.upper()}"
    if count_open_positions(trades) >= MAX_OPEN_POSITIONS: return False, f"MAX_OPEN_{MAX_OPEN_POSITIONS}"
    return True, "OK"


def build_metadata(wallex_data, news_sentiment, iran_impact, rsi, rsi_source, rsi_report, rsi_valid, rsi_validity_status, legacy_rsi, legacy_source, legacy_report, extras, btc_change_6h_avg, btc_change_6h_oldest, btc_change_24h_avg, btc_change_24h_oldest, regime_avg, regime_oldest, signals_if_avg, signals_if_oldest):
    return {
        "code_version": CODE_VERSION, "run_time": datetime.now().isoformat(),
        "rsi_source": rsi_source, "rsi_value": rsi, "rsi_report": rsi_report, "rsi_valid": rsi_valid,
        "rsi_validity_status": rsi_validity_status, "rsi_coverage_pct": rsi_report.get("coverage_pct") if rsi_report else None,
        "legacy_rsi_value": legacy_rsi, "legacy_rsi_source": legacy_source,
        "news_global_sentiment": news_sentiment["sentiment"], "iran_sentiment": iran_impact["sentiment"],
        "wallex_btc_last": wallex_data["btc"]["last"],
        "btc_change_6h_avg": round(btc_change_6h_avg, 4), "btc_change_6h_oldest": round(btc_change_6h_oldest, 4),
        "btc_change_24h_avg": round(btc_change_24h_avg, 4), "btc_change_24h_oldest": round(btc_change_24h_oldest, 4),
        "regime_avg": regime_avg, "regime_oldest": regime_oldest,
        "signals_if_avg": signals_if_avg, "signals_if_oldest": signals_if_oldest, "extras": extras,
    }


def make_trade(side, entry_price, signal_type, btc_change_6h, rsi, amount_toman, metadata, shadow_type=None, reason=None):
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    if side.lower() == "buy":
        stop_price = entry_price * (1 - STOP_LOSS_PERCENT / 100)
        target_price = entry_price * (1 + TAKE_PROFIT_PERCENT / 100)
    else:
        stop_price = entry_price * (1 + STOP_LOSS_PERCENT / 100)
        target_price = entry_price * (1 - TAKE_PROFIT_PERCENT / 100)
    now = datetime.now()
    base = {
        "date": now.date().isoformat(), "time": now.isoformat(), "entry_time": now.isoformat(),
        "side": side, "signal_type": signal_type, "exchange": "wallex", "symbol": WALLEX_SYMBOL,
        "btc_change_6h_at_entry": round(btc_change_6h, 2), "rsi_at_entry": rsi,
        "entry_price": entry_price, "stop_price": stop_price, "target_price": target_price,
        "amount_toman": amount_toman, "max_risk_toman": risk_toman,
        "stop_loss_percent": STOP_LOSS_PERCENT, "effective_risk_percent": EFFECTIVE_RISK_PERCENT,
        "estimated_costs_percent": TOTAL_COST_PERCENT, "btc_volume": round(amount_toman / entry_price, 8),
        "status": "open", "is_paper": True, "profit_toman": 0.0, "profit_pct": 0.0,
        "profit_net_toman": 0.0, "profit_net_pct": 0.0, "gross_pnl": 0.0, "net_pnl": 0.0, "metadata": metadata,
    }
    if shadow_type:
        base.update({"id": f"shadow_{uuid.uuid4().hex[:8]}", "shadow_type": shadow_type, "reason": reason, "is_shadow": True, "decision_path": f"shadow_{shadow_type}"})
    else: base["decision_path"] = "paper_executed"
    return base


def make_rejected_candidate(reason_code, reason_detail, side, signal_type, entry_price, btc_change_6h, rsi, metadata, open_count_at_time):
    trade = make_trade(side, entry_price, signal_type, btc_change_6h, rsi, calculate_position_size(signal_type) or MAX_TRADE_TOMAN, metadata, f"rejected_{reason_code}", reason_detail)
    trade.update({"rejection_reason_code": reason_code, "rejection_reason_detail": reason_detail, "open_positions_at_rejection": open_count_at_time})
    return trade


def get_today_paper_trades(trades):
    return [t for t in trades if t.get("date") == datetime.now().date().isoformat()]


def can_trade_today(trades):
    return len(get_today_paper_trades(trades)) < MAX_DAILY_TRADES


async def main():
    if not acquire_lock(): return
    try:
        now = datetime.now()
        print("=== GLOBAL NEWS ===")
        news_titles, feed_counts = get_all_news()
        news_sentiment = analyze_sentiment(news_titles)
        save_news_history(news_sentiment, feed_counts, news_titles, now)

        print("=== IRAN NEWS ===")
        iran_impact = get_iran_news_impact()

        print("=== PRICES ===")
        wallex = get_wallex_prices()
        if not wallex: print("CANNOT GET WALLEX - EXIT"); return
        btc_tmn = wallex["btc"]["last"]

        btc_usdt = get_btc_usdt()
        
        dollar_data = get_dollar_change_and_update_history(wallex, now)

        btc_data, btc_sha = load_from_github(BTC_HISTORY_FILE)
        btc_history = [(datetime.fromisoformat(t), p) for t, p in btc_data] if btc_data else []

        btc_change_6h = calculate_btc_change(btc_history, btc_tmn, now, BTC_LOOKBACK_SHORT)
        btc_change_24h = calculate_btc_change(btc_history, btc_tmn, now, BTC_LOOKBACK_LONG)
        btc_change_6h_oldest = calculate_btc_change_oldest(btc_history, btc_tmn, now, BTC_LOOKBACK_SHORT)
        btc_change_24h_oldest = calculate_btc_change_oldest(btc_history, btc_tmn, now, BTC_LOOKBACK_LONG)

        if not btc_history or btc_history[-1][1] != btc_tmn:
            btc_history.append((now, btc_tmn))
            btc_history[:] = [(t, p) for t, p in btc_history if now - t < timedelta(hours=BTC_HISTORY_MAX_HOURS)]
            save_to_github(BTC_HISTORY_FILE, [(t.isoformat(), p) for t, p in btc_history], btc_sha)

        print("=== RSI ===")
        rsi, rsi_source, rsi_report = get_rsi_from_wallex_ohlc(hours=WALLEX_OHLC_HOURS)
        rsi_valid, rsi_validity_status, rsi_coverage = compute_rsi_validity(rsi, rsi_source, rsi_report)
        legacy_rsi, legacy_source, legacy_report = get_legacy_rsi_from_btc_history(btc_history)

        candles_1m = get_wallex_ohlc_1m(hours=WALLEX_OHLC_HOURS)
        buckets_15m = resample_1m_to_15m_ohlcv(candles_1m)[0] if candles_1m else []
        extras = compute_metadata_extras(buckets_15m, wallex, now)
        extras.update({"dollar_last": dollar_data.get("dollar_last"), "dollar_6h_change_pct": dollar_data.get("dollar_6h_change_pct"), "dollar_24h_change_pct": dollar_data.get("dollar_24h_change_pct")})

        regime_avg = classify_regime(btc_change_24h)
        regime_oldest = classify_regime(btc_change_24h_oldest)
        signals_if_avg = compute_hypothetical_signal(btc_change_6h, btc_change_24h, rsi, rsi_valid)
        signals_if_oldest = compute_hypothetical_signal(btc_change_6h_oldest, btc_change_24h_oldest, rsi, rsi_valid)

        paper_data, _ = load_from_github(PAPER_TRADES_FILE)
        paper_trades_list = paper_data if paper_data else []
        open_count = count_open_positions(paper_trades_list)

        shadow_data, _ = load_from_github(SHADOW_TRADES_FILE)
        shadow_list = shadow_data if shadow_data else []

        side, signal_type = classify_signal_btc(btc_change_6h, btc_change_24h, rsi, rsi_valid=rsi_valid)
        print(f"SIGNAL: {side} ({signal_type})")

        metadata = build_metadata(wallex, news_sentiment, iran_impact, rsi, rsi_source, rsi_report, rsi_valid, rsi_validity_status, legacy_rsi, legacy_source, legacy_report, extras, btc_change_6h, btc_change_6h_oldest, btc_change_24h, btc_change_24h_oldest, regime_avg, regime_oldest, signals_if_avg, signals_if_oldest)

        shadow_changed = False

        if side:
            can_open, reason = can_open_new_position(paper_trades_list, side)
            if not can_open:
                print(f"SKIP: {reason}")
                rej = make_rejected_candidate(reason.lower(), reason, side, signal_type, wallex["btc"]["ask"] if side=="buy" else wallex["btc"]["bid"], btc_change_6h, rsi, metadata, open_count)
                shadow_list.append(rej); shadow_changed = True
            elif not can_trade_today(paper_trades_list):
                rej = make_rejected_candidate("daily_limit", "MAX_DAILY_TRADES", side, signal_type, wallex["btc"]["ask"] if side=="buy" else wallex["btc"]["bid"], btc_change_6h, rsi, metadata, open_count)
                shadow_list.append(rej); shadow_changed = True
            else:
                amount_toman = calculate_position_size(signal_type)
                entry_price = wallex["btc"]["ask"] if side == "buy" else wallex["btc"]["bid"]
                trade = make_trade(side, entry_price, signal_type, btc_change_6h, rsi, amount_toman, metadata)
                paper_trades_list.append(trade)
                save_to_github(PAPER_TRADES_FILE, paper_trades_list)
                
                msg = (f"🟢 M2 Paper Trade: BUY (DIP)\n\n"
                       f"🏦 last: {_fmt(btc_tmn)} | entry: {_fmt(entry_price)}\n"
                       f"🛑 SL: {_fmt(trade['stop_price'])} | 🎯 TP: {_fmt(trade['target_price'])}\n"
                       f"💵 مبلغ: {_fmt(amount_toman)}\n"
                       f"📊 RSI: {rsi}\n"
                       f"{WARNING_MSG}")
                await bot.send_message(CHAT_ID, msg)
                print("TRADE EXECUTED")

        if len(shadow_list) > MAX_SHADOW_TRADES:
            shadow_list = [s for s in shadow_list if s.get("status") == "open"] + [s for s in shadow_list if s.get("status") == "closed"][-200:]
            shadow_changed = True

        if shadow_changed: save_to_github(SHADOW_TRADES_FILE, shadow_list)

        try:
            anchor = {"last_run_utc": datetime.now().isoformat(), "lock_date": "2026-10-17", "code_version": CODE_VERSION, "btc_history_records": len(btc_history)}
            save_to_github(TIME_ANCHOR_FILE, anchor)
            print("TIME_ANCHOR SAVED")
        except Exception as e: print(f"TIME_ANCHOR ERROR: {e}")

    finally:
        release_lock()


asyncio.run(main())
