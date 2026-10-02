import asyncio
import websockets
import json
import os
import base64
import time
import uuid
import random
import socket
import requests
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
ABAN_API_KEY = os.environ.get("ABAN_API_KEY", "")

HISTORY_FILE = "dollar_history.json"
BTC_HISTORY_FILE = "btc_history.json"
PAPER_TRADES_FILE = "paper_trades.json"
PRICE_COMPARISON_FILE = "price_comparison.json"
LOCK_FILE = "lock.json"

LOCK_MAX_AGE_SECONDS = 720

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PERCENT = 0.10
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_PERCENT  # 0.6%

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

STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3.0
EFFECTIVE_RISK_PERCENT = STOP_LOSS_PERCENT + TOTAL_COST_PERCENT

BTC_LOOKBACK_SHORT = 6
BTC_LOOKBACK_LONG = 24
MAX_DATA_AGE_SECONDS = 300

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

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این Paper Trading است. معامله واقعی انجام نمی‌شود."


# ═══════════════════════════════════════════
# DNS Override for AbanTether
# ═══════════════════════════════════════════
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


def calculate_net_profit(gross_change_pct, amount_toman):
    net_pct = gross_change_pct - TOTAL_COST_PERCENT
    net_toman = (net_pct / 100) * amount_toman
    return round(net_pct, 4), round(net_toman, 0)


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


def get_wallex_price():
    try:
        url = f"{WALLEX_API_URL}/v1/markets"
        fetch_start = datetime.now()
        r = request_with_retry(url, max_retries=3, timeout=15)
        if not r:
            print("WALLEX: no response")
            return None
        fetch_end = datetime.now()
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = symbols.get(WALLEX_SYMBOL, {})
        stats = btc.get("stats", {})
        if not stats:
            print(f"WALLEX: no stats")
            return None
        last_price = float(stats.get("lastPrice", 0))
        bid = float(stats.get("bidPrice", 0))
        ask = float(stats.get("askPrice", 0))
        data_age = (fetch_end - fetch_start).total_seconds()
        print(f"WALLEX: last={last_price:,.0f} | bid={bid:,.0f} | ask={ask:,.0f} | age={data_age:.2f}s")
        if data_age > MAX_DATA_AGE_SECONDS:
            print(f"DATA TOO OLD")
            return None
        return {
            "last": last_price, "bid": bid, "ask": ask,
            "spread_pct": ((ask - bid) / bid * 100) if bid else 0,
            "fetch_end": fetch_end.isoformat(),
            "data_age_seconds": round(data_age, 2),
        }
    except Exception as e:
        print(f"WALLEX ERROR: {type(e).__name__}: {e}")
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
                        print(f"NOBITEX: last={mid:,.0f} | bid={best_bid:,.0f} | ask={best_ask:,.0f}")
                        return {"last": mid, "bid": best_bid, "ask": best_ask}
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        print(f"NOBITEX WS ERROR: {type(e).__name__}: {e}")
    return None


async def get_nobitex_price(max_attempts=3):
    for attempt in range(max_attempts):
        try:
            print(f"NOBITEX WS ATTEMPT {attempt+1}/{max_attempts}")
            return await run_nobitex_ws()
        except Exception as e:
            print(f"NOBITEX WS FAILED: {type(e).__name__}: {e}")
        if attempt < max_attempts - 1:
            delay = min(30, 2 ** (attempt + 1)) + random.uniform(0, 1)
            await asyncio.sleep(delay)
    return None


def get_aban_price():
    """قیمت BTC/IRT از آبان‌تتر (OTC)"""
    if not ABAN_API_KEY:
        print("ABAN: API KEY NOT SET - SKIP")
        return None
    try:
        headers = {
            "Authorization": ABAN_API_KEY,
            "Content-Type": "application/json",
        }
        fetch_start = datetime.now()
        r = requests.get(ABAN_TICKER_URL, headers=headers, timeout=15)
        fetch_end = datetime.now()
        if r.status_code != 200:
            print(f"ABAN: Status {r.status_code} - {r.text[:200]}")
            return None
        data = r.json()
        btc = data.get("data", {}).get("markets", {}).get("BTCIRT", {})
        if not btc:
            print(f"ABAN: no BTCIRT")
            return None
        buy = float(btc.get("buy_price", 0))   # ask (user buys)
        sell = float(btc.get("sell_price", 0)) # bid (user sells)
        mid = (buy + sell) / 2
        data_age = (fetch_end - fetch_start).total_seconds()
        print(f"ABAN: buy={buy:,.0f} | sell={sell:,.0f} | mid={mid:,.0f} | age={data_age:.2f}s")
        return {
            "buy": buy,      # ask
            "sell": sell,    # bid
            "mid": mid,
            "spread_pct": ((buy - sell) / sell * 100) if sell else 0,
            "fetch_end": fetch_end.isoformat(),
            "data_age_seconds": round(data_age, 2),
        }
    except Exception as e:
        print(f"ABAN ERROR: {type(e).__name__}: {e}")
        return None


def save_price_comparison(wallex, nobitex, aban, now):
    if not wallex:
        print("SKIP comparison (no wallex)")
        return
    try:
        entry = {
            "time": now.isoformat(),
            "wallex_last": wallex["last"],
            "wallex_bid": wallex["bid"],
            "wallex_ask": wallex["ask"],
            "wallex_spread_pct": round(wallex["spread_pct"], 4),
        }

        # Nobitex
        if nobitex:
            entry["nobitex_last"] = nobitex["last"]
            entry["nobitex_bid"] = nobitex["bid"]
            entry["nobitex_ask"] = nobitex["ask"]
            # forward: بخر از والکس، بفروش در نوبیتکس
            diff_wn = nobitex["bid"] - wallex["ask"]
            entry["wallex_to_nobitex"] = round(diff_wn, 0)
            entry["wallex_to_nobitex_pct"] = round((diff_wn / wallex["ask"]) * 100, 4)
            # reverse: بخر از نوبیتکس، بفروش در والکس
            diff_nw = wallex["bid"] - nobitex["ask"]
            entry["nobitex_to_wallex"] = round(diff_nw, 0)
            entry["nobitex_to_wallex_pct"] = round((diff_nw / nobitex["ask"]) * 100, 4)

        # Aban
        if aban:
            entry["aban_buy"] = aban["buy"]
            entry["aban_sell"] = aban["sell"]
            entry["aban_mid"] = aban["mid"]
            entry["aban_spread_pct"] = round(aban["spread_pct"], 4)
            # forward: بخر از والکس، بفروش به آبان
            diff_wa = aban["sell"] - wallex["ask"]
            entry["wallex_to_aban"] = round(diff_wa, 0)
            entry["wallex_to_aban_pct"] = round((diff_wa / wallex["ask"]) * 100, 4)
            # reverse: بخر از آبان، بفروش در والکس
            diff_aw = wallex["bid"] - aban["buy"]
            entry["aban_to_wallex"] = round(diff_aw, 0)
            entry["aban_to_wallex_pct"] = round((diff_aw / aban["buy"]) * 100, 4)
            # aban ↔ nobitex
            if nobitex:
                diff_an = nobitex["bid"] - aban["buy"]
                entry["aban_to_nobitex"] = round(diff_an, 0)
                entry["aban_to_nobitex_pct"] = round((diff_an / aban["buy"]) * 100, 4)
                diff_na = aban["sell"] - nobitex["ask"]
                entry["nobitex_to_aban"] = round(diff_na, 0)
                entry["nobitex_to_aban_pct"] = round((diff_na / nobitex["ask"]) * 100, 4)

        data, sha = load_from_github(PRICE_COMPARISON_FILE)
        history = data if data else []
        history.append(entry)
        cutoff = (now - timedelta(days=7)).isoformat()
        history = [h for h in history if h.get("time", "") >= cutoff]
        save_to_github(PRICE_COMPARISON_FILE, history, sha)

        # لاگ خلاصه
        if aban and nobitex:
            print(f"COMPARISON SAVED:")
            print(f"  Wallex→Nobitex: {entry.get('wallex_to_nobitex', 0):+,.0f} ({entry.get('wallex_to_nobitex_pct', 0):+.4f}%)")
            print(f"  Wallex→Aban:    {entry.get('wallex_to_aban', 0):+,.0f} ({entry.get('wallex_to_aban_pct', 0):+.4f}%)")
            print(f"  Aban→Wallex:    {entry.get('aban_to_wallex', 0):+,.0f} ({entry.get('aban_to_wallex_pct', 0):+.4f}%)")
        elif aban:
            print(f"COMPARISON SAVED (with aban)")
        elif nobitex:
            print(f"COMPARISON SAVED (with nobitex)")
    except Exception as e:
        print(f"COMPARISON ERROR: {type(e).__name__}: {e}")


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
                else:
                    print(f"STALE LOCK ({age:.0f}s) - OVERRIDING")
            except Exception as e:
                print(f"LOCK PARSE ERROR: {e} - OVERRIDING")
        new_lock = {"time": now.isoformat(), "id": str(uuid.uuid4()), "max_age_seconds": LOCK_MAX_AGE_SECONDS}
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


def calculate_rsi(prices, period=14):
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


def calculate_btc_change(btc_history, current_price, now, lookback_hours):
    if not btc_history or current_price is None:
        return 0.0
    lookback_time = now - timedelta(hours=lookback_hours)
    recent = [(t, p) for t, p in btc_history if t >= lookback_time]
    print(f"  [BTC-CHANGE] lookback={lookback_hours}h, records={len(recent)}")
    if len(recent) >= 1:
        avg_old = sum(p for _, p in recent) / len(recent)
        change = ((current_price - avg_old) / avg_old) * 100
        print(f"  [BTC-CHANGE] avg_old={avg_old:,.0f}, current={current_price:,.0f}, change={change:+.4f}%")
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
        print(f"CONFLICT! BUY={buy_signals} | SELL={sell_signals} → NO TRADE")
        return None, None

    signals = [("buy", s) for s in buy_signals] + [("sell", s) for s in sell_signals]
    if not signals:
        return None, None

    for priority_signal in SIGNAL_PRIORITY:
        for side, sig in signals:
            if sig == priority_signal:
                print(f"ACTIVE: {signals} → SELECTED: {side}/{sig}")
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


def paper_trade(side, btc_toman_price, signal_type, btc_change_6h, rsi, wallex_data):
    amount_toman = calculate_position_size(signal_type)
    if amount_toman is None:
        return None
    risk_toman = MAX_RISK_TABLE.get(signal_type, DEFAULT_MAX_RISK)
    btc_volume = round(amount_toman / btc_toman_price, 8)

    if side.lower() == "buy":
        stop_price = btc_toman_price * (1 - STOP_LOSS_PERCENT / 100)
        target_price = btc_toman_price * (1 + TAKE_PROFIT_PERCENT / 100)
    else:
        stop_price = btc_toman_price * (1 + STOP_LOSS_PERCENT / 100)
        target_price = btc_toman_price * (1 - TAKE_PROFIT_PERCENT / 100)

    now = datetime.now()
    return {
        "date": now.date().isoformat(),
        "time": now.isoformat(),
        "side": side,
        "signal_type": signal_type,
        "exchange": "wallex",
        "symbol": WALLEX_SYMBOL,
        "entry_data_timestamp": wallex_data.get("fetch_end"),
        "entry_data_age_seconds": wallex_data.get("data_age_seconds"),
        "btc_change_6h_at_entry": round(btc_change_6h, 2),
        "rsi_at_entry": rsi,
        "entry_price": btc_toman_price,
        "entry_price_toman": btc_toman_price,
        "entry_price_irr": btc_toman_price * IRR_TO_TOMAN,
        "irr_to_toman": IRR_TO_TOMAN,
        "stop_price": stop_price,
        "target_price": target_price,
        "take_profit_price": target_price,
        "amount_toman": amount_toman,
        "max_risk_toman": risk_toman,
        "stop_loss_percent": STOP_LOSS_PERCENT,
        "effective_risk_percent": EFFECTIVE_RISK_PERCENT,
        "estimated_costs_percent": TOTAL_COST_PERCENT,
        "btc_volume": btc_volume,
        "status": "open",
        "is_paper": True,
        "profit_toman": 0.0,
        "profit_pct": 0.0,
        "profit_net_toman": 0.0,
        "profit_net_pct": 0.0,
    }


def get_today_paper_trades(trades):
    today = datetime.now().date().isoformat()
    return [t for t in trades if t.get("date") == today]


def can_trade_today(trades):
    return len(get_today_paper_trades(trades)) < MAX_DAILY_TRADES


async def main():
    if not acquire_lock():
        print("ANOTHER INSTANCE RUNNING - EXIT")
        return
    try:
        now = datetime.now()

        wallex = get_wallex_price()
        if not wallex:
            print("CANNOT GET WALLEX PRICE - EXIT")
            return
        btc_toman = wallex["last"]

        nobitex = await get_nobitex_price()
        aban = get_aban_price()

        save_price_comparison(wallex, nobitex, aban, now)

        btc_data, btc_sha = load_from_github(BTC_HISTORY_FILE)
        btc_history = [(datetime.fromisoformat(t), p) for t, p in btc_data] if btc_data else []
        print(f"BTC_HISTORY LOADED: {len(btc_history)} records")

        btc_change_6h = calculate_btc_change(btc_history, btc_toman, now, BTC_LOOKBACK_SHORT)
        btc_change_24h = calculate_btc_change(btc_history, btc_toman, now, BTC_LOOKBACK_LONG)
        print(f"BTC_CHANGE_6H: {btc_change_6h:+.2f}%")
        print(f"BTC_CHANGE_24H: {btc_change_24h:+.2f}%")

        if not btc_history or btc_history[-1][1] != btc_toman:
            btc_history.append((now, btc_toman))
            btc_history[:] = [(t, p) for t, p in btc_history if now - t < timedelta(hours=48)]
            save_to_github(BTC_HISTORY_FILE, [(t.isoformat(), p) for t, p in btc_history], btc_sha)
            print(f"BTC_HISTORY UPDATED")
        else:
            print(f"BTC_HISTORY UNCHANGED")

        if len(btc_history) >= 15:
            prices = [p for _, p in btc_history]
            rsi = calculate_rsi(prices)
            print(f"RSI (from our BTC history): {rsi}")
        else:
            prices = get_btc_history_coingecko(14)
            rsi = calculate_rsi(prices)
            print(f"RSI (from CoinGecko fallback): {rsi}")

        paper_data, paper_sha = load_from_github(PAPER_TRADES_FILE)
        paper_trades_list = paper_data if paper_data else []
        open_count = count_open_positions(paper_trades_list)
        print(f"PAPER TRADES: {len(paper_trades_list)} total, {open_count} open")

        for t in paper_trades_list:
            if t.get("status") != "open":
                continue
            entry = t["entry_price"]
            side = t.get("side", "").lower()
            amount = t.get("amount_toman", 50000)
            change_pct = ((btc_toman - entry) / entry * 100) if side == "buy" else ((entry - btc_toman) / entry * 100)

            if change_pct <= -STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None

            if action:
                net_pct, net_toman = calculate_net_profit(change_pct, amount)
                t["status"] = "closed"
                t["exit_price"] = btc_toman
                t["exit_price_toman"] = btc_toman
                t["exit_price_irr"] = btc_toman * IRR_TO_TOMAN
                t["exit_time"] = now.isoformat()
                t["exit_reason"] = action
                t["profit_pct"] = change_pct
                t["profit_toman"] = (change_pct / 100) * amount
                t["profit_net_toman"] = net_toman
                t["profit_net_pct"] = net_pct
                print(f"PAPER {action.upper()}: gross={change_pct:+.2f}% | net={net_pct:+.2f}%")

        side, signal_type = classify_signal_btc(btc_change_6h, btc_change_24h, rsi)
        print(f"SIGNAL: {side} ({signal_type})")

        if side:
            can_open, reason = can_open_new_position(paper_trades_list, side)
            if not can_open:
                print(f"SKIP: {reason}")
            elif not can_trade_today(paper_trades_list):
                print("DAILY LIMIT REACHED")
            else:
                trade = paper_trade(side, btc_toman, signal_type, btc_change_6h, rsi, wallex)
                if trade is None:
                    print(f"SIGNAL TOO WEAK - SKIP")
                else:
                    paper_trades_list.append(trade)
                    save_to_github(PAPER_TRADES_FILE, paper_trades_list, paper_sha)

                    emoji = "🟢" if side == "buy" else "🔴"
                    type_fa = {
                        "VERY_STRONG": "خیلی قوی", "STRONG": "قوی", "MEDIUM": "متوسط",
                        "MOMENTUM": "مومنتوم", "DIP": "کف‌گیری", "TOP": "سقف‌گیری"
                    }.get(signal_type, signal_type)

                    amount = trade["amount_toman"]
                    risk = trade["max_risk_toman"]

                    # مقایسه سه‌گانه
                    comparison_lines = ""
                    if aban:
                        diff_wa = aban["sell"] - wallex["ask"]
                        diff_wa_pct = (diff_wa / wallex["ask"]) * 100
                        comparison_lines += f"\n  والکس→آبان: {diff_wa:+,.0f} ({diff_wa_pct:+.3f}%)"
                    if nobitex:
                        diff_wn = nobitex["bid"] - wallex["ask"]
                        diff_wn_pct = (diff_wn / wallex["ask"]) * 100
                        comparison_lines += f"\n  والکس→نوبیتکس: {diff_wn:+,.0f} ({diff_wn_pct:+.3f}%)"

                    msg = (
                        f"{emoji} Paper Trade: {side.upper()} ({type_fa})\n\n"
                        f"🏦 صرافی: والکس ({WALLEX_SYMBOL})\n"
                        f"💰 BTC: {_fmt(btc_toman)} تومان\n"
                        f"🛑 حد ضرر: {_fmt(trade.get('stop_price'))} ({STOP_LOSS_PERCENT}%)\n"
                        f"🎯 حد سود: {_fmt(trade.get('target_price'))} ({TAKE_PROFIT_PERCENT}%)\n"
                        f"💵 مبلغ: {_fmt(amount)} تومان\n"
                        f"⚠️ ریسک: {_fmt(risk)} تومان (مؤثر {EFFECTIVE_RISK_PERCENT}%)\n"
                        f"📉 هزینه: {TOTAL_COST_PERCENT}%\n"
                        f"📈 تغییر ۶h: {btc_change_6h:+.2f}%\n"
                        f"📊 RSI: {rsi}\n"
                        f"📊 مقایسه:{comparison_lines}\n"
                        f"{WARNING_MSG}"
                    )
                    await bot.send_message(CHAT_ID, msg)
                    print(f"PAPER TRADE EXECUTED: {side} ({signal_type}) | Size: {_fmt(amount)}")
        else:
            print(f"NO SIGNAL - RSI={rsi} - BTC_CHANGE_6H={btc_change_6h:+.2f}%")
    finally:
        release_lock()


asyncio.run(main())
