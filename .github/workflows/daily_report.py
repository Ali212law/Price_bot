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
TRADES_FILE = "trades_history.json"

MAX_DAILY_LOSS_TOMAN = 50000

bot = Client(BALE_TOKEN)

def request_with_retry(url, headers=None, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                print(f"NOT FOUND (no retry): {url[:60]}")
                return r
            print(f"RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries} - Error: {e}")
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
            return json.loads(content)
        return None
    except Exception as e:
        print(f"LOAD ERROR ({filename}): {e}")
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
    trades_data = load_from_github(TRADES_FILE)

    today = datetime.now().date().isoformat()

    if not trades_data:
        print("NO TRADES FILE")
        msg = (
            f"📊 گزارش روزانه — {today}\n\n"
            f"ℹ️ امروز معامله‌ای انجام نشد.\n"
            f"💡 دلیل: سیگنال قوی پیدا نشد."
        )
        send_message(msg)
        return

    today_trades = [t for t in trades_data if t.get("date") == today]
    print(f"TODAY TRADES: {len(today_trades)}")

    if not today_trades:
        msg = (
            f"📊 گزارش روزانه — {today}\n\n"
            f"ℹ️ امروز معامله‌ای انجام نشد.\n"
            f"💡 دلیل: سیگنال قوی پیدا نشد."
        )
        send_message(msg)
        return

    total_profit = 0
    closed_trades = []
    open_trades = []

    for t in today_trades:
        if t.get("status") == "closed":
            closed_trades.append(t)
            total_profit += t.get("profit_toman", 0)
        else:
            open_trades.append(t)

    total = len(today_trades)
    closed_count = len(closed_trades)
    open_count = len(open_trades)
    win_count = len([t for t in closed_trades if t.get("profit_toman", 0) > 0])
    loss_count = len([t for t in closed_trades if t.get("profit_toman", 0) < 0])

    if total_profit > 0:
        profit_emoji = "🟢"
    elif total_profit < 0:
        profit_emoji = "🔴"
    else:
        profit_emoji = "⚪"

    msg = (
        f"📊 گزارش روزانه — {today}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📈 کل معاملات: {total}\n"
        f"✅ بسته‌شده: {closed_count}\n"
        f"⏳ باز: {open_count}\n"
        f"🟢 برنده: {win_count}\n"
        f"🔴 بازنده: {loss_count}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{profit_emoji} سود/ضرر کل: {total_profit:,.0f} تومان\n\n"
    )

    if open_trades:
        msg += "📋 معاملات باز:\n"
        for t in open_trades:
            side = t.get("side", "?")
            price = t.get("price", 0)
            msg += f"• {side} @ {price:,.0f}\n"
        msg += "\n"

    if total_profit <= -MAX_DAILY_LOSS_TOMAN:
        msg += (
            f"🚨 هشدار!\n"
            f"ضرر روزانه از حد مجاز ({MAX_DAILY_LOSS_TOMAN:,.0f} تومان) گذشته است.\n"
            f"توصیه: TRADING_ENABLED را False کنید."
        )

    send_message(msg)
    print("REPORT SENT")

if __name__ == "__main__":
    main()
