import asyncio
import websockets
import json
import os
import base64
import time
import uuid
import random
import requests
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
HISTORY_FILE = "dollar_history.json"
BTC_HISTORY_FILE = "btc_history.json"
PAPER_TRADES_FILE = "paper_trades.json"
LOCK_FILE = "lock.json"

MAX_TRADE_TOMAN = 50000
MAX_DAILY_TRADES = 5
STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3

BTC_LOOKBACK_SHORT = 6
BTC_LOOKBACK_LONG = 24

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

WS_URL = "wss://ws.nobitex.ir/connection/websocket"
IRR_TO_TOMAN = 10

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این Paper Trading است. معامله واقعی انجام نمی‌شود."


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


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


async def run_ws_session():
    async with websockets.connect(
        WS_URL, open_timeout=15, close_timeout=5, ping_interval=20, ping_timeout=20,
    ) as ws:
        await ws.send('{"connect": {}, "id": 1}')
        await asyncio.wait_for(ws.recv(), timeout=10)
        await ws.send(json.dumps({"subscribe": {"channel": "public:orderbook-BTCIRT"}, "id": 2}))
        for i in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
                data = json.loads(msg)
                if "push" in data:
                    asks = data["push"]["pub"]["data"]["asks"]
                    bids = data["push"]["pub"]["data"]["bids"]
                    best_ask_toman = float(asks[0][0]) / IRR_TO_TOMAN
                    best_bid_toman = float(bids[0][0]) / IRR_TO_TOMAN
                    mid_price_toman = (best_ask_toman + best_bid_toman) / 2
                    print(f"MID_PRICE_TOMAN: {mid_price_toman:,.0f}")
                    return mid_price_toman
            except asyncio.TimeoutError:
                continue
    return None


async def get_btc_price_ws(max_attempts=5):
    for attempt in range(max_attempts):
        try:
            print(f"WS ATTEMPT {attempt+1}/{max_attempts}")
            return await run_ws_session()
        except (asyncio.TimeoutError, OSError, websockets.exceptions.WebSocketException) as exc:
            print(f"WS FAILED: {type(exc).__name__} - {exc}")
            if attempt == max_attempts - 1:
                return None
            delay = min(30, 2 ** (attempt + 1)) + random.uniform(0, 1)
            print(f"WS RETRY in {delay:.1f}s")
            await asyncio.sleep(delay)
    return None


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
            lock_time = datetime.fromisoformat(lock_data.get("time", "2000-01-01"))
            if (now - lock_time).total_seconds() < 120:
                print("LOCK EXISTS - SKIP")
                return False
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


def get_dollar_toman():
    try:
        r = request_with_retry("https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl")
        if r:
            raw = float(r.json()["data"][0][1].replace(",", ""))
            return raw / 10
    except Exception as e:
        print(f"DOLLAR ERROR: {e}")
    return None


def calculate_btc_change(btc_history, current_price, now, lookback_hours):
    if not btc_history or current_price is None:
        return 0.0
    lookback_time = now - timedelta(hours=lookback_hours)
    recent = [(t, p) for t, p in btc_history if t >= lookback_time]
    print(f"  [BTC-CHANGE] lookback={lookback_hours}h, records_in_window={len(recent)}")
    if len(recent) >= 1:
        avg_old = sum(p for _, p in recent) / len(recent)
        change = ((current_price - avg_old) / avg_old) * 100
        print(f"  [BTC-CHANGE] avg_old={avg_old:,.0f}, current={current_price:,.0f}, change={change:+.4f}%")
        return change
    return 0.0


def classify_signal_btc(btc_change_6h, btc_change_24h, rsi):
    """
    FIX: side رو با حروف کوچیک برمی‌گردونه برای سازگاری با monitor.py
    """
    if rsi is None:
        rsi = 50

    if rsi < RSI_OVERSOLD and btc_change_6h >= THRESHOLD_VERY_STRONG:
        return "buy", "VERY_STRONG"
    if rsi < RSI_LOW and btc_change_6h >= THRESHOLD_STRONG:
        return "buy", "STRONG"
    if rsi < RSI_MILD_LOW and btc_change_6h >= THRESHOLD_MEDIUM:
        return "buy", "MEDIUM"
    if btc_change_6h >= THRESHOLD_MOMENTUM:
        return "buy", "MOMENTUM"
    if rsi < RSI_OVERSOLD:
        return "buy", "DIP"

    if rsi > RSI_OVERBOUGHT and btc_change_6h <= -THRESHOLD_VERY_STRONG:
        return "sell", "VERY_STRONG"
    if rsi > RSI_HIGH and btc_change_6h <= -THRESHOLD_STRONG:
        return "sell", "STRONG"
    if rsi > RSI_MILD_HIGH and btc_change_6h <= -THRESHOLD_MEDIUM:
        return "sell", "MEDIUM"
    if btc_change_6h <= -THRESHOLD_MOMENTUM:
        return "sell", "MOMENTUM"
    if rsi > RSI_OVERBOUGHT:
        return "sell", "TOP"

    return None, None


def has_open_position_in_direction(trades, side):
    # FIX: case-insensitive
    side = side.lower()
    return any(
        t.get("status") == "open" and t.get("side", "").lower() == side
        for t in trades
    )


def count_open_positions(trades):
    return len([t for t in trades if t.get("status") == "open"])


def paper_trade(side, btc_toman_price, signal_type, btc_change_6h, rsi):
    """
    FIX: side.lower() برای مقایسه‌ی case-insensitive
    """
    btc_volume = round(MAX_TRADE_TOMAN / btc_toman_price, 8)
    if side.lower() == "buy":
        stop_price = btc_toman_price * (1 - STOP_LOSS_PERCENT / 100)
        target_price = btc_toman_price * (1 + TAKE_PROFIT_PERCENT / 100)
    else:
        stop_price = btc_toman_price * (1 + STOP_LOSS_PERCENT / 100)
        target_price = btc_toman_price * (1 - TAKE_PROFIT_PERCENT / 100)
    return {
        "date": datetime.now().date().isoformat(),
        "time": datetime.now().isoformat(),
        "side": side,  # ← با حروف کوچیک ذخیره می‌شه
        "signal_type": signal_type,
        "btc_change_6h_at_entry": round(btc_change_6h, 2),
        "rsi_at_entry": rsi,
        "entry_price": btc_toman_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "take_profit_price": target_price,
        "btc_volume": btc_volume,
        "amount_toman": MAX_TRADE_TOMAN,
        "status": "open",
        "is_paper": True,
        "profit_toman": 0.0,
        "profit_pct": 0.0,
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

        btc_toman = await get_btc_price_ws()
        if btc_toman:
            print(f"BTC_TOMAN: {btc_toman:,.0f}")
        else:
            print("CANNOT GET BTC PRICE - EXIT")
            return

        dollar_toman = get_dollar_toman()
        if dollar_toman:
            print(f"DOLLAR_TOMAN: {dollar_toman:,.0f}")

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
            print(f"BTC_HISTORY UPDATED (added new record)")
        else:
            print(f"BTC_HISTORY UNCHANGED")

        if dollar_toman:
            dollar_data, dollar_sha = load_from_github(HISTORY_FILE)
            dollar_history = [(datetime.fromisoformat(t), p) for t, p in dollar_data] if dollar_data else []
            if not dollar_history or dollar_history[-1][1] != dollar_toman:
                dollar_history.append((now, dollar_toman))
                dollar_history[:] = [(t, p) for t, p in dollar_history if now - t < timedelta(hours=48)]
                save_to_github(HISTORY_FILE, [(t.isoformat(), p) for t, p in dollar_history], dollar_sha)

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
            side = t.get("side", "").lower()  # FIX: case-insensitive
            change_pct = ((btc_toman - entry) / entry * 100) if side == "buy" else ((entry - btc_toman) / entry * 100)
            if change_pct <= -STOP_LOSS_PERCENT:
                t["status"] = "closed"
                t["exit_price"] = btc_toman
                t["exit_time"] = now.isoformat()
                t["exit_reason"] = "stop_loss"
                t["profit_pct"] = change_pct
                t["profit_toman"] = change_pct / 100 * t["amount_toman"]
                print(f"PAPER STOP LOSS: {change_pct:+.2f}%")
            elif change_pct >= TAKE_PROFIT_PERCENT:
                t["status"] = "closed"
                t["exit_price"] = btc_toman
                t["exit_time"] = now.isoformat()
                t["exit_reason"] = "take_profit"
                t["profit_pct"] = change_pct
                t["profit_toman"] = change_pct / 100 * t["amount_toman"]
                print(f"PAPER TAKE PROFIT: {change_pct:+.2f}%")

        side, signal_type = classify_signal_btc(btc_change_6h, btc_change_24h, rsi)
        print(f"SIGNAL: {side} ({signal_type})")

        if side:
            if has_open_position_in_direction(paper_trades_list, side):
                print(f"ALREADY HAVE OPEN {side.upper()} POSITION - SKIP")
            elif not can_trade_today(paper_trades_list):
                print("DAILY LIMIT REACHED")
            else:
                trade = paper_trade(side, btc_toman, signal_type, btc_change_6h, rsi)
                paper_trades_list.append(trade)
                save_to_github(PAPER_TRADES_FILE, paper_trades_list, paper_sha)
                emoji = "🟢" if side == "buy" else "🔴"
                type_fa = {
                    "VERY_STRONG": "خیلی قوی",
                    "STRONG": "قوی",
                    "MEDIUM": "متوسط",
                    "MOMENTUM": "مومنتوم",
                    "DIP": "کف‌گیری",
                    "TOP": "سقف‌گیری"
                }.get(signal_type, signal_type)
                dollar_line = f"📊 دلار: {dollar_toman:,.0f} تومان\n" if dollar_toman else ""
                msg = (
                    f"{emoji} Paper Trade: {side.upper()} ({type_fa})\n\n"
                    f"💰 BTC: {_fmt(btc_toman)} تومان\n"
                    f"🛑 حد ضرر: {_fmt(trade.get('stop_price'))}\n"
                    f"🎯 حد سود: {_fmt(trade.get('target_price'))}\n"
                    f"💵 مبلغ: {MAX_TRADE_TOMAN:,.0f}\n\n"
                    f"📈 تغییر ۶h: {btc_change_6h:+.2f}%\n"
                    f"📊 RSI: {rsi}\n"
                    f"{dollar_line}\n"
                    f"{WARNING_MSG}"
                )
                await bot.send_message(CHAT_ID, msg)
                print(f"PAPER TRADE EXECUTED: {side} ({signal_type})")
        else:
            print(f"NO SIGNAL - RSI={rsi} - BTC_CHANGE_6H={btc_change_6h:+.2f}%")
    finally:
        release_lock()


asyncio.run(main())
