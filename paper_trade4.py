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
PAPER_TRADES_FILE = "paper_trades.json"
LOCK_FILE = "lock.json"

MAX_TRADE_TOMAN = 50000
MAX_DAILY_TRADES = 5
STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3

WS_URL = "wss://ws.nobitex.ir/connection/websocket"
IRR_TO_TOMAN = 10

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این Paper Trading است. معامله واقعی انجام نمی‌شود."

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

def classify_signal(dollar_change, rsi):
    """طبقه‌بندی سیگنال بر اساس دلار و RSI"""
    
    # ===== سیگنال خرید =====
    if dollar_change >= 5.0 and rsi and rsi < 30:
        return "BUY", "VERY_STRONG"
    if dollar_change >= 3.0 and rsi and rsi < 40:
        return "BUY", "STRONG"
    if dollar_change >= 2.0 and rsi and rsi < 50:
        return "BUY", "MEDIUM"
    if dollar_change >= 3.0:
        return "BUY", "SIMPLE_STRONG"
    if dollar_change >= 2.0:
        return "BUY", "SIMPLE_MEDIUM"
    
    # ===== سیگنال فروش =====
    if dollar_change <= -5.0 and rsi and rsi > 75:
        return "SELL", "VERY_STRONG"
    if dollar_change <= -3.0 and rsi and rsi > 70:
        return "SELL", "STRONG"
    if dollar_change <= -2.0 and rsi and rsi > 65:
        return "SELL", "MEDIUM"
    if dollar_change <= -3.0:
        return "SELL", "SIMPLE_STRONG"
    if dollar_change <= -2.0:
        return "SELL", "SIMPLE_MEDIUM"
    
    return None, None

def paper_trade(side, btc_toman_price, signal_type, dollar_change, rsi):
    btc_volume = round(MAX_TRADE_TOMAN / btc_toman_price, 8)
    stop_price = btc_toman_price * (1 - STOP_LOSS_PERCENT / 100) if side == "buy" else None
    target_price = btc_toman_price * (1 + TAKE_PROFIT_PERCENT / 100) if side == "buy" else None
    return {
        "date": datetime.now().date().isoformat(),
        "time": datetime.now().isoformat(),
        "side": side,
        "signal_type": signal_type,
        "dollar_change_at_entry": round(dollar_change, 2),
        "rsi_at_entry": rsi,
        "entry_price": btc_toman_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "btc_volume": btc_volume,
        "amount_toman": MAX_TRADE_TOMAN,
        "status": "open",
        "is_paper": True
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
        dollar_toman = None
        btc_toman = None
        r = request_with_retry("https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl")
        if r:
            dollar_toman = float(r.json()["data"][0][1].replace(",", ""))
            print(f"DOLLAR_TOMAN: {dollar_toman}")
        btc_toman = await get_btc_price_ws()
        if btc_toman:
            print(f"BTC_TOMAN: {btc_toman:,.0f}")
        btc_history = get_btc_history(14)
        rsi = calculate_rsi(btc_history)
        print(f"RSI: {rsi}")
        data, sha = load_from_github(HISTORY_FILE)
        history = [(datetime.fromisoformat(t), p) for t, p in data] if data else []
        now = datetime.now()
        if dollar_toman:
            history.append((now, dollar_toman))
            history[:] = [(t, p) for t, p in history if now - t < timedelta(hours=24)]
            save_to_github(HISTORY_FILE, [(t.isoformat(), p) for t, p in history], sha)
        dollar_change = 0
        if len(history) >= 2 and dollar_toman:
            old_dollar = history[0][1]
            dollar_change = ((dollar_toman - old_dollar) / old_dollar) * 100
        print(f"DOLLAR_CHANGE: {dollar_change:+.2f}%")
        paper_data, paper_sha = load_from_github(PAPER_TRADES_FILE)
        paper_trades_list = paper_data if paper_data else []
        print(f"PAPER TRADES: {len(paper_trades_list)}")
        
        # بررسی معاملات باز
        for t in paper_trades_list:
            if t.get("status") != "open":
                continue
            if btc_toman is None:
                continue
            entry = t["entry_price"]
            side = t["side"]
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
        
        # طبقه‌بندی سیگنال
        side, signal_type = classify_signal(dollar_change, rsi)
        print(f"SIGNAL: {side} ({signal_type})")
        
        if dollar_toman and btc_toman and side:
            if can_trade_today(paper_trades_list):
                trade = paper_trade(side, btc_toman, signal_type, dollar_change, rsi)
                paper_trades_list.append(trade)
                save_to_github(PAPER_TRADES_FILE, paper_trades_list, paper_sha)
                
                emoji = "🟢" if side == "buy" else "🔴"
                
                # ترجمه نوع سیگنال
                type_fa = {
                    "VERY_STRONG": "خیلی قوی",
                    "STRONG": "قوی",
                    "MEDIUM": "متوسط",
                    "SIMPLE_STRONG": "ساده قوی",
                    "SIMPLE_MEDIUM": "ساده متوسط"
                }.get(signal_type, signal_type)
                
                msg = f"""{emoji} Paper Trade: {side} ({type_fa})

💰 قیمت: {btc_toman:,.0f}
🛑 حد ضرر: {trade['stop_price']:,.0f}
🎯 حد سود: {trade['target_price']:,.0f}
💵 مبلغ: {MAX_TRADE_TOMAN:,.0f}

📊 دلار: {dollar_change:+.2f}%
📊 RSI: {rsi}

{WARNING_MSG}"""
                await bot.send_message(CHAT_ID, msg)
                print(f"PAPER TRADE EXECUTED: {side} ({signal_type})")
            else:
                print("DAILY LIMIT")
        else:
            print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")
        
        save_to_github(PAPER_TRADES_FILE, paper_trades_list, paper_sha)
    finally:
        release_lock()

asyncio.run(main())
