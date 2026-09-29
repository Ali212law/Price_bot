import asyncio
import websockets
import json
import os
import base64
import re
import time
import uuid
import requests
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
HISTORY_FILE = "dollar_history.json"
TRADES_FILE = "trades_history.json"
LOCK_FILE = "lock.json"
SIGNAL_THRESHOLD = 2.0
TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False") == "True"

MAX_TRADE_TOMAN = 50000
MAX_DAILY_TRADES = 1
MAX_DAILY_LOSS_TOMAN = 50000
STOP_LOSS_PERCENT = 1
TAKE_PROFIT_PERCENT = 2

WS_URL = "wss://ws.nobitex.ir/connection/websocket"

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ توجه: قیمت BTC از WebSocket نوبیتکس، تحلیل تکنیکال از CoinGecko."

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

async def get_btc_price_ws():
    """دریافت قیمت BTC از WebSocket نوبیتکس"""
    try:
        async with websockets.connect(WS_URL) as ws:
            print("WS Connected")
            await ws.send('{"connect": {}, "id": 1}')
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            subscribe_msg = {
                "subscribe": {"channel": "public:orderbook-BTCIRT"},
                "id": 2
            }
            await ws.send(json.dumps(subscribe_msg))
            
            for i in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    data = json.loads(msg)
                    if "push" in data:
                        asks = data["push"]["pub"]["data"]["asks"]
                        bids = data["push"]["pub"]["data"]["bids"]
                        best_ask = float(asks[0][0])
                        best_bid = float(bids[0][0])
                        mid_price = (best_ask + best_bid) / 2
                        print(f"WS PRICE: {mid_price}")
                        return mid_price
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        print(f"WS ERROR: {type(e).__name__} - {e}")
    return None

def get_btc_history(days=14):
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
    if len(prices) < period + 1:
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

def calculate_ma(prices, period=7):
    if len(prices) < period:
        return None
    try:
        return round(sum(prices[-period:]) / period, 2)
    except:
        return None

def get_news():
    try:
        r = request_with_retry("https://cointelegraph.com/rss")
        if not r:
            return []
        content = r.text
        titles = re.findall(r"<title>(.*?)</title>", content)
        titles = [t for t in titles if "Cointelegraph" not in t and len(t) > 20]
        return titles[:3]
    except Exception as e:
        print(f"NEWS ERROR: {e}")
        return []

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

def save_to_github(filename, data, sha):
    try:
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
        print(f"SAVE ERROR ({filename})")
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

async def main():
    if not acquire_lock():
        print("ANOTHER INSTANCE RUNNING - EXIT")
        return

    try:
        dollar = None
        btc_toman = None

        r = request_with_retry("https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl")
        if r:
            dollar = float(r.json()["data"][0][1].replace(",", ""))
            print(f"DOLLAR: {dollar}")

        btc_toman = await get_btc_price_ws()

        btc_history = get_btc_history(14)
        rsi = calculate_rsi(btc_history)
        ma7 = calculate_ma(btc_history, 7)
        print(f"RSI: {rsi}")
        print(f"MA7: {ma7}")

        news = get_news()
        print(f"NEWS: {len(news)} items")

        data, sha = load_from_github(HISTORY_FILE)
        history = [(datetime.fromisoformat(t), p) for t, p in data] if data else []
        print(f"LOADED: {len(history)} records")

        now = datetime.now()
        if dollar:
            history.append((now, dollar))
            history[:] = [(t, p) for t, p in history if now - t < timedelta(hours=24)]
            save_to_github(HISTORY_FILE, [(t.isoformat(), p) for t, p in history], sha)

        dollar_change = 0
        if len(history) >= 2 and dollar:
            old_dollar = history[0][1]
            dollar_change = ((dollar - old_dollar) / old_dollar) * 100
        print(f"DOLLAR CHANGE: {dollar_change:+.2f}%")

        signal = None
        if dollar_change >= SIGNAL_THRESHOLD and rsi and rsi < 40:
            signal = "BUY"
        elif dollar_change <= -SIGNAL_THRESHOLD and rsi and rsi > 60:
            signal = "SELL"
        elif dollar_change >= SIGNAL_THRESHOLD:
            signal = "BUY_SIMPLE"
        elif dollar_change <= -SIGNAL_THRESHOLD:
            signal = "SELL_SIMPLE"

        news_section = ""
        if news:
            news_section = "\n\n📰 اخبار اخیر:\n"
            for n in news[:2]:
                news_section += f"• {n[:80]}\n"

        if dollar and btc_toman and signal in ["BUY", "SELL"]:
            print(f"STRONG SIGNAL: {signal}")
            msg = f"🟢 سیگنال {signal} قوی!\n\n💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n📊 RSI: {rsi}\n🟠 BTC: {btc_toman:,.0f}{news_section}\n\n⚠️ معامله غیرفعال ({TRADING_ENABLED})\n{WARNING_MSG}"
            await bot.send_message(CHAT_ID, msg)
        else:
            print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")

    finally:
        release_lock()

asyncio.run(main())
