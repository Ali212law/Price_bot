import requests
import json
import os
import base64
import time
from datetime import datetime
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
ABAN_API_KEY = os.environ.get("ABAN_API_KEY", "")
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"

PAPER_TRADES_FILE = "paper_trades.json"        # Paper Trading
LIVE_TRADES_FILE = "trades_history.json"        # Live Trading

TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False").strip().lower() == "true"

# === SL/TP برای Paper (مطابق paper_trade12.py) ===
PAPER_STOP_LOSS_PERCENT = 1.5
PAPER_TAKE_PROFIT_PERCENT = 3.0

# === SL/TP برای Live (مطابق قبلی monitor.py) ===
LIVE_STOP_LOSS_PERCENT = 1.0
LIVE_TAKE_PROFIT_PERCENT = 2.0

WS_URL = "wss://ws.nobitex.ir/connection/websocket"
IRR_TO_TOMAN = 10

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این پیام برای مدیریت معاملات است."


# ========== HELPERS ==========
def request_with_retry(url, headers=None, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            print(f"RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries} - Error: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
            print(f"PUT RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"PUT RETRY {attempt+1}/{max_retries} - Error: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
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


def send_message(text):
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": text}
        r = requests.post(url, data=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None


# ========== PRICE ==========
async def get_btc_price_nobitex():
    """قیمت BTC/IRT از نوبیتکس WebSocket"""
    try:
        import websockets
        import asyncio

        async def run_ws():
            async with websockets.connect(
                WS_URL, open_timeout=15, close_timeout=5,
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
                            return (best_ask + best_bid) / 2
                    except asyncio.TimeoutError:
                        continue
            return None

        return await run_ws()
    except Exception as e:
        print(f"WS ERROR: {e}")
        return None


# ========== PLACE ORDER (Live) ==========
def place_order(side, btc_toman_price, amount_toman):
    """ثبت سفارش واقعی — فقط اگه TRADING_ENABLED=True"""
    if not TRADING_ENABLED:
        print(f"TRADING DISABLED - WOULD PLACE {side.upper()}")
        return True  # برای Paper، همیشه موفق

    if not ABAN_API_KEY:
        print("NO ABAN_API_KEY - CANNOT PLACE ORDER")
        return False

    try:
        btc_volume = round(amount_toman / btc_toman_price, 8)
        url = "https://api.abantether.com/api/v1/order_handler/order"
        headers = {
            "Authorization": ABAN_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "side": side,
            "base_symbol": "BTC",
            "quote_symbol": "IRT",
            "amount": btc_volume,
            "price": btc_toman_price,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code in [200, 201]:
            print(f"ORDER PLACED: {side} - {btc_volume} BTC")
            return True
        print(f"ORDER FAILED: {r.status_code} - {r.text[:200]}")
        return False
    except Exception as e:
        print(f"ORDER ERROR: {e}")
        return False


# ========== CHECK PAPER TRADES ==========
def check_paper_trades(btc_toman, now):
    """چک کردن پوزیشن‌های Paper Trading"""
    print("\n=== CHECK PAPER TRADES ===")
    trades, sha = load_from_github(PAPER_TRADES_FILE)
    if not trades:
        print("NO PAPER TRADES")
        return

    open_trades = [t for t in trades if t.get("status") == "open"]
    print(f"OPEN PAPER TRADES: {len(open_trades)}")

    if not open_trades:
        print("NO OPEN PAPER TRADES")
        return

    changed = False
    for t in trades:
        if t.get("status") != "open":
            continue

        entry = t["entry_price"]
        side = t.get("side", "").lower()
        amount = t["amount_toman"]

        if side == "buy":
            change_pct = ((btc_toman - entry) / entry) * 100
            if change_pct <= -PAPER_STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= PAPER_TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None
        elif side == "sell":
            change_pct = ((entry - btc_toman) / entry) * 100
            if change_pct <= -PAPER_STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= PAPER_TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None
        else:
            print(f"UNKNOWN SIDE: {side}")
            continue

        if action:
            print(f"PAPER {action.upper()}: {change_pct:+.2f}%")
            t["status"] = "closed"
            t["exit_price"] = btc_toman
            t["exit_time"] = now.isoformat()
            t["exit_reason"] = action
            t["profit_pct"] = change_pct
            if side == "buy":
                t["profit_toman"] = (btc_toman - entry) / entry * amount
            else:
                t["profit_toman"] = (entry - btc_toman) / entry * amount
            changed = True

            emoji = "🟢" if change_pct > 0 else "🔴"
            action_fa = "حد سود" if action == "take_profit" else "حد ضرر"
            msg = (
                f"{emoji} Paper معامله بسته شد! ({action_fa})\n\n"
                f"💰 ورود: {entry:,.0f} تومان\n"
                f"💰 خروج: {btc_toman:,.0f} تومان\n"
                f"📊 تغییر: {change_pct:+.2f}%\n"
                f"💵 سود/ضرر: {t['profit_toman']:,.0f} تومان\n"
                f"📈 سیگنال: {t.get('signal_type', '?')}\n\n"
                f"{WARNING_MSG}"
            )
            send_message(msg)

    if changed:
        save_to_github(PAPER_TRADES_FILE, trades, sha)
        print("PAPER TRADES UPDATED")
    else:
        print("NO CHANGES")


# ========== CHECK LIVE TRADES ==========
def check_live_trades(btc_toman, now):
    """چک کردن پوزیشن‌های Live Trading"""
    print("\n=== CHECK LIVE TRADES ===")
    trades, sha = load_from_github(LIVE_TRADES_FILE)
    if not trades:
        print("NO LIVE TRADES")
        return

    open_trades = [t for t in trades if t.get("status") == "open"]
    print(f"OPEN LIVE TRADES: {len(open_trades)}")

    if not open_trades:
        print("NO OPEN LIVE TRADES")
        return

    changed = False
    for t in trades:
        if t.get("status") != "open":
            continue

        entry = t["entry_price"]
        side = t.get("side", "").lower()
        amount = t["amount_toman"]

        if side == "buy":
            change_pct = ((btc_toman - entry) / entry) * 100
            if change_pct <= -LIVE_STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= LIVE_TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None
        elif side == "sell":
            change_pct = ((entry - btc_toman) / entry) * 100
            if change_pct <= -LIVE_STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= LIVE_TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None
        else:
            continue

        if action:
            print(f"LIVE {action.upper()}: {change_pct:+.2f}%")

            # ثبت سفارش واقعی
            result = place_order("buy" if side == "sell" else "sell",
                                 btc_toman, amount)
            if not result:
                print("ORDER FAILED - KEEP POSITION OPEN")
                continue

            t["status"] = "closed"
            t["exit_price"] = btc_toman
            t["exit_time"] = now.isoformat()
            t["exit_reason"] = action
            t["profit_pct"] = change_pct
            t["profit_toman"] = change_pct / 100 * amount
            changed = True

            emoji = "🟢" if change_pct > 0 else "🔴"
            action_fa = "حد سود" if action == "take_profit" else "حد ضرر"
            msg = (
                f"{emoji} معامله واقعی بسته شد! ({action_fa})\n\n"
                f"💰 ورود: {entry:,.0f} تومان\n"
                f"💰 خروج: {btc_toman:,.0f} تومان\n"
                f"📊 تغییر: {change_pct:+.2f}%\n"
                f"💵 سود/ضرر: {t['profit_toman']:,.0f} تومان"
            )
            send_message(msg)

    if changed:
        save_to_github(LIVE_TRADES_FILE, trades, sha)
        print("LIVE TRADES UPDATED")
    else:
        print("NO CHANGES")


# ========== MAIN ==========
def main():
    import asyncio

    print("=== MONITOR 2 ===")
    now = datetime.now()

    # قیمت BTC
    btc_toman = asyncio.run(get_btc_price_nobitex())
    if not btc_toman:
        print("CANNOT GET BTC PRICE - EXIT")
        return
    print(f"BTC_TOMAN: {btc_toman:,.0f}")

    # چک Paper Trades
    check_paper_trades(btc_toman, now)

    # چک Live Trades
    check_live_trades(btc_toman, now)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
