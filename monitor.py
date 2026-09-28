import requests
import json
import os
import base64
from datetime import datetime
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
ABAN_API_KEY = os.environ["ABAN_API_KEY"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
TRADES_FILE = "trades_history.json"
TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False") == "True"

STOP_LOSS_PERCENT = 1
TAKE_PROFIT_PERCENT = 2

bot = Client(BALE_TOKEN)
WARNING_MSG = "⚠️ توجه: قیمت BTC از صرافی داخلی (آبان‌تتر) گرفته شده است."

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
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
        r = requests.put(url, headers=headers, json=payload, timeout=10)
        if r.status_code in [200, 201]:
            print(f"SAVED: {filename}")
        else:
            print(f"SAVE ERROR ({filename}): {r.status_code}")
    except Exception as e:
        print(f"SAVE ERROR ({filename}): {e}")

def get_btc_price():
    try:
        headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}
        r = requests.get("https://api.abantether.com/api/v1/manager/otc/ticker", headers=headers, timeout=10)
        data = r.json()
        btc_data = data["data"]["markets"]["BTCIRT"]
        return (float(btc_data["buy_price"]) + float(btc_data["sell_price"])) / 2
    except Exception as e:
        print(f"BTC PRICE ERROR: {e}")
        return None

def place_order(side, btc_toman_price, amount_toman):
    try:
        btc_volume = round(amount_toman / btc_toman_price, 8)
        url = "https://api.abantether.com/api/v1/order_handler/order"
        headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}
        payload = {
            "side": side,
            "base_symbol": "BTC",
            "quote_symbol": "IRT",
            "price": str(int(btc_toman_price)),
            "volume": str(btc_volume)
        }
        print(f"PLACING ORDER: {side} - {btc_volume} BTC @ {btc_toman_price}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        return r.json()
    except Exception as e:
        print(f"ORDER ERROR: {e}")
        return None

def send_message(text):
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": text}
        r = requests.post(url, data=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None

def main():
    trades_data, trades_sha = load_from_github(TRADES_FILE)
    if not trades_data:
        print("NO TRADES FILE")
        return

    trades = trades_data
    open_trades = [t for t in trades if t.get("status") == "open"]
    print(f"OPEN TRADES: {len(open_trades)}")

    if not open_trades:
        print("NO OPEN TRADES - EXIT")
        return

    btc_toman = get_btc_price()
    if not btc_toman:
        print("CANNOT GET BTC PRICE - EXIT")
        return
    print(f"BTC_TOMAN: {btc_toman}")

    changed = False
    for i, trade in enumerate(trades):
        if trade.get("status") != "open":
            continue

        entry_price = trade["price"]
        side = trade["side"]
        amount_toman = trade["amount_toman"]

        if side == "buy":
            change_pct = ((btc_toman - entry_price) / entry_price) * 100
            if change_pct <= -STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None

            if action:
                if not TRADING_ENABLED:
                    print(f"TRADING DISABLED - WOULD {action}")
                    continue

                print(f"{action.upper()}: {change_pct:+.2f}%")
                result = place_order("sell", btc_toman, amount_toman)

                if result:
                    trades[i]["status"] = "closed"
                    trades[i]["exit_price"] = btc_toman
                    trades[i]["exit_time"] = datetime.now().isoformat()
                    trades[i]["exit_reason"] = action
                    trades[i]["profit_pct"] = change_pct
                    trades[i]["profit_toman"] = (btc_toman - entry_price) / entry_price * amount_toman
                    changed = True

                    emoji = "🟢" if change_pct > 0 else "🔴"
                    action_text = "حد سود" if action == "take_profit" else "حد ضرر"
                    msg = (
                        f"{emoji} معامله بسته شد! ({action_text})\n\n"
                        f"💰 ورود: {entry_price:,.0f} تومان\n"
                        f"💰 خروج: {btc_toman:,.0f} تومان\n"
                        f"📊 تغییر: {change_pct:+.2f}٪\n"
                        f"💵 سود/ضرر: {trades[i]['profit_toman']:,.0f} تومان\n\n"
                        f"{WARNING_MSG}"
                    )
                    send_message(msg)

        elif side == "sell":
            change_pct = ((entry_price - btc_toman) / entry_price) * 100
            if change_pct <= -STOP_LOSS_PERCENT:
                action = "stop_loss"
            elif change_pct >= TAKE_PROFIT_PERCENT:
                action = "take_profit"
            else:
                action = None

            if action:
                if not TRADING_ENABLED:
                    print(f"TRADING DISABLED - WOULD {action}")
                    continue

                print(f"{action.upper()}: {change_pct:+.2f}%")
                result = place_order("buy", btc_toman, amount_toman)

                if result:
                    trades[i]["status"] = "closed"
                    trades[i]["exit_price"] = btc_toman
                    trades[i]["exit_time"] = datetime.now().isoformat()
                    trades[i]["exit_reason"] = action
                    trades[i]["profit_pct"] = change_pct
                    trades[i]["profit_toman"] = (entry_price - btc_toman) / entry_price * amount_toman
                    changed = True

                    emoji = "🟢" if change_pct > 0 else "🔴"
                    action_text = "حد سود" if action == "take_profit" else "حد ضرر"
                    msg = (
                        f"{emoji} معامله بسته شد! ({action_text})\n\n"
                        f"💰 ورود: {entry_price:,.0f} تومان\n"
                        f"💰 خروج: {btc_toman:,.0f} تومان\n"
                        f"📊 تغییر: {change_pct:+.2f}٪\n"
                        f"💵 سود/ضرر: {trades[i]['profit_toman']:,.0f} تومان\n\n"
                        f"{WARNING_MSG}"
                    )
                    send_message(msg)

    if changed:
        save_to_github(TRADES_FILE, trades, trades_sha)
        print("TRADES UPDATED")
    else:
        print("NO CHANGES")

if __name__ == "__main__":
    main()
