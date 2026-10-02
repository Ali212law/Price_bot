import requests
import json
import os
import base64
import time
from datetime import datetime
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"

PAPER_TRADES_FILE = "paper_trades.json"
LIVE_TRADES_FILE = "trades_history.json"

TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False").strip().lower() == "true"

STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3.0

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"

bot = Client(BALE_TOKEN)


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def request_with_retry(url, headers=None, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries}: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
        except Exception as e:
            print(f"PUT RETRY: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def load_from_github(filename, silent_404=False):
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
        print(f"LOAD ERROR: {e}")
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
        print(f"SAVE ERROR: {e}")
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


def get_wallex_prices():
    """برمی‌گردونه: bid, ask, last"""
    try:
        url = f"{WALLEX_API_URL}/v1/markets"
        r = request_with_retry(url, max_retries=3, timeout=15)
        if not r or r.status_code != 200:
            return None
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = symbols.get(WALLEX_SYMBOL, {})
        stats = btc.get("stats", {})
        if not stats:
            return None
        return {
            "last": float(stats.get("lastPrice", 0)),
            "bid": float(stats.get("bidPrice", 0)),
            "ask": float(stats.get("askPrice", 0)),
        }
    except Exception as e:
        print(f"WALLEX ERROR: {e}")
        return None


def calculate_net_profit(gross_change_pct, amount_toman):
    net_pct = gross_change_pct - TOTAL_COST_PERCENT
    net_toman = (net_pct / 100) * amount_toman
    return round(net_pct, 4), round(net_toman, 0)


def place_order(side, btc_toman_price, amount_toman):
    if not TRADING_ENABLED:
        print(f"TRADING DISABLED - WOULD PLACE {side.upper()}")
        return True
    print(f"LIVE ORDER NOT IMPLEMENTED")
    return False


def check_paper_trades(prices, now):
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

        # FIX: BUY close با bid, SELL close با ask
        if side == "buy":
            exit_price = prices["bid"]
            change_pct = ((exit_price - entry) / entry) * 100
        else:
            exit_price = prices["ask"]
            change_pct = ((entry - exit_price) / entry) * 100

        if change_pct <= -STOP_LOSS_PERCENT:
            action = "stop_loss"
        elif change_pct >= TAKE_PROFIT_PERCENT:
            action = "take_profit"
        else:
            action = None

        if action:
            net_pct, net_toman = calculate_net_profit(change_pct, amount)
            t["status"] = "closed"
            t["exit_price"] = exit_price
            t["exit_price_toman"] = exit_price
            t["exit_price_irr"] = exit_price * 10
            t["exit_time"] = now.isoformat()
            t["exit_reason"] = action
            t["profit_pct"] = change_pct
            t["profit_toman"] = (change_pct / 100) * amount
            t["profit_net_toman"] = net_toman
            t["profit_net_pct"] = net_pct
            changed = True
            print(f"PAPER {action.upper()}: gross={change_pct:+.2f}% | net={net_pct:+.2f}%")

            emoji = "🟢" if change_pct > 0 else "🔴"
            action_fa = "حد سود" if action == "take_profit" else "حد ضرر"
            msg = (
                f"{emoji} Paper معامله بسته شد! ({action_fa})\n\n"
                f"📈 سیگنال: {t.get('signal_type', '?')}\n"
                f"💵 ورود: {_fmt(entry)}\n"
                f"💵 خروج: {_fmt(exit_price)}\n"
                f"📊 تغییر خام: {change_pct:+.2f}%\n"
                f"📉 هزینه: -{TOTAL_COST_PERCENT}%\n"
                f"✅ سود/ضرر خالص: {_fmt(net_toman)} ({net_pct:+.2f}%)\n"
                f"💰 حجم: {_fmt(amount)}"
            )
            send_message(msg)

    if changed:
        save_to_github(PAPER_TRADES_FILE, trades, sha)
        print("PAPER TRADES UPDATED")
    else:
        print("NO CHANGES")


def check_live_trades(prices, now):
    print("\n=== CHECK LIVE TRADES ===")
    trades, sha = load_from_github(LIVE_TRADES_FILE, silent_404=True)
    if not trades:
        print("NO LIVE TRADES")
        return
    print("LIVE NOT IMPLEMENTED YET")


def main():
    print("=== MONITOR 7 ===")
    now = datetime.now()

    prices = get_wallex_prices()
    if not prices:
        print("CANNOT GET PRICES")
        return
    print(f"WALLEX: bid={prices['bid']:,.0f} | ask={prices['ask']:,.0f} | last={prices['last']:,.0f}")

    check_paper_trades(prices, now)
    check_live_trades(prices, now)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
