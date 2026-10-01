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

PAPER_TRADES_FILE = "paper_trades.json"
LIVE_TRADES_FILE = "trades_history.json"

TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False").strip().lower() == "true"

PAPER_STOP_LOSS_PERCENT = 1.5
PAPER_TAKE_PROFIT_PERCENT = 3.0

LIVE_STOP_LOSS_PERCENT = 1.0
LIVE_TAKE_PROFIT_PERCENT = 2.0

WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ این پیام برای مدیریت معاملات است."


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def request_with_retry(url, headers=None, max_retries=3, timeout=10):
    """
    FIX: اگه 404 بود، فوراً برگردون (بدون retry)
    """
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r   # ← فایل وجود نداره، retry بی‌فایده‌ست
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


def load_from_github(filename, silent_404=False):
    """
    FIX: اگه فایل نبود (404)، بدون خطا None برگردون
    """
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = request_with_retry(url, headers=headers)
        if r and r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        if r and r.status_code == 404:
            if not silent_404:
                print(f"FILE NOT FOUND: {filename}")
        return None, None
    except Exception as e:
        print(f"LOAD ERROR ({filename}): {e}")
        return None, None


def save_to_github(filename, data, sha=None):
    try:
        if not sha:
            _, sha = load_from_github(filename, silent_404=True)
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


def get_wallex_price():
    """قیمت BTC/TMN از والکس"""
    try:
        url = f"{WALLEX_API_URL}/v1/markets"
        r = request_with_retry(url, max_retries=3, timeout=15)
        if not r or r.status_code != 200:
            print("WALLEX: no response")
            return None

        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = symbols.get(WALLEX_SYMBOL, {})
        stats = btc.get("stats", {})

        if not stats:
            print(f"WALLEX: no stats for {WALLEX_SYMBOL}")
            return None

        last_price = float(stats.get("lastPrice", 0))
        print(f"WALLEX {WALLEX_SYMBOL}: last={last_price:,.0f}")
        return last_price
    except Exception as e:
        print(f"WALLEX ERROR: {type(e).__name__}: {e}")
        return None


def place_order(side, btc_toman_price, amount_toman):
    if not TRADING_ENABLED:
        print(f"TRADING DISABLED - WOULD PLACE {side.upper()}")
        return True
    print(f"LIVE ORDER NOT IMPLEMENTED YET")
    return False


def check_paper_trades(btc_toman, now):
    print("\n=== CHECK PAPER TRADES ===")
    trades, sha = load_from_github(PAPER_TRADES_FILE)
    if not trades:
        print("NO PAPER TRADES FILE")
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
        amount = t.get("amount_toman", 50000)

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
            t["profit_toman"] = change_pct / 100 * amount
            changed = True

            emoji = "🟢" if change_pct > 0 else "🔴"
            action_fa = "حد سود" if action == "take_profit" else "حد ضرر"
            msg = (
                f"{emoji} Paper معامله بسته شد! ({action_fa})\n\n"
                f"🏦 صرافی: والکس\n"
                f"💰 ورود: {_fmt(entry)} تومان\n"
                f"💰 خروج: {_fmt(btc_toman)} تومان\n"
                f"📊 تغییر: {change_pct:+.2f}%\n"
                f"💵 سود/ضرر: {_fmt(t['profit_toman'])} تومان\n"
                f"📈 سیگنال: {t.get('signal_type', '?')}"
            )
            send_message(msg)

    if changed:
        save_to_github(PAPER_TRADES_FILE, trades, sha)
        print("PAPER TRADES UPDATED")
    else:
        print("NO CHANGES")


def check_live_trades(btc_toman, now):
    print("\n=== CHECK LIVE TRADES ===")
    trades, sha = load_from_github(LIVE_TRADES_FILE, silent_404=True)
    if not trades:
        print("NO LIVE TRADES (file not found - normal)")
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
                f"💰 ورود: {_fmt(entry)} تومان\n"
                f"💰 خروج: {_fmt(btc_toman)} تومان\n"
                f"📊 تغییر: {change_pct:+.2f}%\n"
                f"💵 سود/ضرر: {_fmt(t['profit_toman'])} تومان"
            )
            send_message(msg)

    if changed:
        save_to_github(LIVE_TRADES_FILE, trades, sha)
        print("LIVE TRADES UPDATED")
    else:
        print("NO CHANGES")


def main():
    print("=== MONITOR 4 ===")
    now = datetime.now()

    btc_toman = get_wallex_price()
    if not btc_toman:
        print("CANNOT GET WALLEX PRICE - EXIT")
        return
    print(f"BTC_TOMAN: {btc_toman:,.0f}")

    check_paper_trades(btc_toman, now)
    check_live_trades(btc_toman, now)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
