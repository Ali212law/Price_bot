import requests
import asyncio
import json
import os
import base64
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
ABAN_API_KEY = os.environ["ABAN_API_KEY"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"
HISTORY_FILE = "dollar_history.json"
SIGNAL_THRESHOLD = 2.0

bot = Client(BALE_TOKEN)

# ===== تحلیل تکنیکال =====

def get_btc_history(days=14):
    """دریافت قیمت تاریخی بیت‌کوین از CoinGecko"""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
        r = requests.get(url, timeout=15)
        data = r.json()
        prices = [p[1] for p in data["prices"]]
        return prices
    except Exception as e:
        print(f"BTC HISTORY ERROR: {e}")
        return []

def calculate_rsi(prices, period=14):
    """محاسبه RSI"""
    if len(prices) < period + 1:
        return None
    try:
        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    except Exception as e:
        print(f"RSI ERROR: {e}")
        return None

def calculate_ma(prices, period=7):
    """محاسبه میانگین متحرک"""
    if len(prices) < period:
        return None
    try:
        return round(sum(prices[-period:]) / period, 2)
    except:
        return None

# ===== ذخیره تاریخچه دلار =====

def load_history_from_github():
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{HISTORY_FILE}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            history_data = json.loads(content)
            return [(datetime.fromisoformat(t), p) for t, p in history_data], data["sha"]
        return [], None
    except Exception as e:
        print(f"LOAD ERROR: {e}")
        return [], None

def save_history_to_github(history, sha):
    try:
        data = [(t.isoformat(), p) for t, p in history]
        content = json.dumps(data)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{HISTORY_FILE}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        payload = {"message": "Update history", "content": content_b64}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=headers, json=payload, timeout=10)
        if r.status_code in [200, 201]:
            print("HISTORY SAVED")
        else:
            print(f"SAVE ERROR: {r.status_code}")
    except Exception as e:
        print(f"SAVE ERROR: {e}")

# ===== دریافت قیمت‌ها =====

async def main():
    dollar = None
    btc = None
    
    # دلار
    try:
        r = requests.get(
            "https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl",
            timeout=10
        )
        dollar = float(r.json()["data"][0][1].replace(",", ""))
        print(f"DOLLAR: {dollar}")
    except Exception as e:
        print(f"DOLLAR ERROR: {e}")
    
    # بیت‌کوین از آبان‌تتر
    try:
        headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}
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
    
    # تحلیل تکنیکال
    btc_history = get_btc_history(14)
    rsi = calculate_rsi(btc_history)
    ma7 = calculate_ma(btc_history, 7)
    
    print(f"RSI: {rsi}")
    print(f"MA7: {ma7}")
    
    # تاریخچه دلار
    history, sha = load_history_from_github()
    print(f"LOADED: {len(history)} records")
    
    now = datetime.now()
    if dollar:
        history.append((now, dollar))
        history[:] = [(t, p) for t, p in history if now - t < timedelta(hours=24)]
        save_history_to_github(history, sha)
    
    # محاسبه تغییر دلار
    dollar_change = 0
    if len(history) >= 2 and dollar:
        old_dollar = history[0][1]
        dollar_change = ((dollar - old_dollar) / old_dollar) * 100
    
    print(f"DOLLAR CHANGE: {dollar_change:+.2f}%")
    
    # سیگنال ترکیبی
    signal = None
    
    # خرید: دلار ۲٪+ گرون شده AND RSI زیر ۴۰
    if dollar_change >= SIGNAL_THRESHOLD and rsi and rsi < 40:
        signal = "BUY"
    # فروش: دلار ۲٪- ارزون شده AND RSI بالای ۶۰
    elif dollar_change <= -SIGNAL_THRESHOLD and rsi and rsi > 60:
        signal = "SELL"
    # سیگنال ساده (فقط دلار)
    elif dollar_change >= SIGNAL_THRESHOLD:
        signal = "BUY_SIMPLE"
    elif dollar_change <= -SIGNAL_THRESHOLD:
        signal = "SELL_SIMPLE"
    
    # ارسال پیام
    if dollar and btc:
        if signal == "BUY":
            msg = (
                f"🟢🟢 سیگنال خرید قوی!\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"📈 MA7: {ma7}\n"
                f"🟠 BTC: {btc:,.0f}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("STRONG BUY")
        elif signal == "SELL":
            msg = (
                f"🔴🔴 سیگنال فروش قوی!\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"📉 MA7: {ma7}\n"
                f"🟠 BTC: {btc:,.0f}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("STRONG SELL")
        elif signal == "BUY_SIMPLE":
            msg = f"🟢 سیگنال خرید (ساده)\n\n💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n📊 RSI: {rsi}\n🟠 BTC: {btc:,.0f}"
            await bot.send_message(CHAT_ID, msg)
            print("SIMPLE BUY")
        elif signal == "SELL_SIMPLE":
            msg = f"🔴 سیگنال فروش (ساده)\n\n💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n📊 RSI: {rsi}\n🟠 BTC: {btc:,.0f}"
            await bot.send_message(CHAT_ID, msg)
            print("SIMPLE SELL")
        else:
            print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")

asyncio.run(main())
