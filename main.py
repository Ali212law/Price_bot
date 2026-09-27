import requests
import asyncio
import json
import os
from datetime import datetime, timedelta
from pyrobale import Client

# خواندن از GitHub Secrets
BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
ABAN_API_KEY = os.environ["ABAN_API_KEY"]

HISTORY_FILE = "dollar_history.json"
SIGNAL_THRESHOLD = 2.0

bot = Client(BALE_TOKEN)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                return [(datetime.fromisoformat(t), p) for t, p in data]
        except:
            return []
    return []

def save_history(history):
    try:
        data = [(t.isoformat(), p) for t, p in history]
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

async def main():
    dollar = None
    btc = None
    
    # دریافت قیمت دلار از TGJU
    try:
        r = requests.get(
            "https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl",
            timeout=10
        )
        dollar = float(r.json()["data"][0][1].replace(",", ""))
        print(f"DOLLAR: {dollar}")
    except Exception as e:
        print(f"DOLLAR ERROR: {e}")
    
    # دریافت قیمت بیت‌کوین از آبان‌تتر
    try:
        headers = {
            "Authorization": ABAN_API_KEY,
            "Content-Type": "application/json"
        }
        r = requests.get(
            "https://api.abantether.com/api/v1/manager/otc/ticker",
            headers=headers,
            timeout=10
        )
        data = r.json()
        btc_data = data["data"]["markets"]["BTCIRT"]
        buy_price = float(btc_data["buy_price"])
        sell_price = float(btc_data["sell_price"])
        btc = (buy_price + sell_price) / 2
        print(f"BTC: {btc}")
    except Exception as e:
        print(f"BTC ERROR: {e}")
    
    # ذخیره تاریخچه
    history = load_history()
    now = datetime.now()
    
    if dollar:
        history.append((now, dollar))
        history[:] = [(t, p) for t, p in history 
                      if now - t < timedelta(hours=24)]
        save_history(history)
    
    # محاسبه سیگنال
    signal = None
    change_pct = 0
    
    if len(history) >= 2 and dollar:
        old_dollar = history[0][1]
        change_pct = ((dollar - old_dollar) / old_dollar) * 100
        
        if change_pct >= SIGNAL_THRESHOLD:
            signal = "BUY"
        elif change_pct <= -SIGNAL_THRESHOLD:
            signal = "SELL"
    
    # ارسال به بله
    if dollar and btc:
        if signal == "BUY":
            msg = f"🟢 سیگنال خرید!\n\n💰 دلار: {dollar:,.0f}\n📈 تغییر: +{change_pct:.2f}٪\n🟠 BTC: {btc:,.0f}"
            await bot.send_message(CHAT_ID, msg)
            print(f"BUY - {change_pct:+.2f}%")
        elif signal == "SELL":
            msg = f"🔴 سیگنال فروش!\n\n💰 دلار: {dollar:,.0f}\n📉 تغییر: {change_pct:.2f}٪\n🟠 BTC: {btc:,.0f}"
            await bot.send_message(CHAT_ID, msg)
            print(f"SELL - {change_pct:+.2f}%")
        else:
            print(f"NO SIGNAL - {dollar:,.0f} - {change_pct:+.2f}%")

asyncio.run(main())
