import requests
import asyncio
import json
import os
import base64
import re
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

WARNING_MSG = "⚠️ توجه: قیمت BTC از صرافی داخلی (آبان‌تتر) و تحلیل تکنیکال از بازار جهانی (CoinGecko) گرفته شده است."

# ===== تحلیل تکنیکال =====

def get_btc_history(days=14):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
        r = requests.get(url, timeout=15)
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

# ===== اخبار =====

def get_news():
    try:
        r = requests.get("https://cointelegraph.com/rss", timeout=15)
        content = r.text

        titles = re.findall(r"<title>(.*?)</title>", content)
        print(f"RAW TITLES: {len(titles)}")

        titles = [t for t in titles if "Cointelegraph" not in t and len(t) > 20]
        print(f"FILTERED: {len(titles)}")

        return titles[:3]
    except Exception as e:
        print(f"NEWS ERROR: {e}")
        return []

# ===== ذخیره تاریخچه =====

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
        content = json.dumps(data)
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

def load_dollar_history():
    data, sha = load_from_github(HISTORY_FILE)
    if data:
        return [(datetime.fromisoformat(t), p) for t, p in data], sha
    return [], None

def save_dollar_history(history, sha):
    data = [(t.isoformat(), p) for t, p in history]
    save_to_github(HISTORY_FILE, data, sha)

# ===== دریافت قیمت‌ها =====

async def main():
    dollar = None
    btc_toman = None

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

    # بیت‌کوین
    try:
        headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}
        r = requests.get(
            "https://api.abantether.com/api/v1/manager/otc/ticker",
            headers=headers,
            timeout=10
        )
        data = r.json()
        btc_data = data["data"]["markets"]["BTCIRT"]
        btc_toman = (float(btc_data["buy_price"]) + float(btc_data["sell_price"])) / 2
        print(f"BTC_TOMAN: {btc_toman}")
    except Exception as e:
        print(f"BTC ERROR: {e}")

    # تکنیکال
    btc_history = get_btc_history(14)
    rsi = calculate_rsi(btc_history)
    ma7 = calculate_ma(btc_history, 7)
    print(f"RSI: {rsi}")
    print(f"MA7: {ma7}")

    # اخبار
    news = get_news()
    print(f"NEWS: {len(news)} items")
    for n in news:
        print(f"  - {n[:60]}")

    # تاریخچه دلار
    history, sha = load_dollar_history()
    print(f"LOADED: {len(history)} records")

    now = datetime.now()
    if dollar:
        history.append((now, dollar))
        history[:] = [(t, p) for t, p in history if now - t < timedelta(hours=24)]
        save_dollar_history(history, sha)

    # تغییر دلار
    dollar_change = 0
    if len(history) >= 2 and dollar:
        old_dollar = history[0][1]
        dollar_change = ((dollar - old_dollar) / old_dollar) * 100
    print(f"DOLLAR CHANGE: {dollar_change:+.2f}%")

    # سیگنال
    signal = None
    if dollar_change >= SIGNAL_THRESHOLD and rsi and rsi < 40:
        signal = "BUY"
    elif dollar_change <= -SIGNAL_THRESHOLD and rsi and rsi > 60:
        signal = "SELL"
    elif dollar_change >= SIGNAL_THRESHOLD:
        signal = "BUY_SIMPLE"
    elif dollar_change <= -SIGNAL_THRESHOLD:
        signal = "SELL_SIMPLE"

    # ساخت بخش اخبار
    news_section = ""
    if news:
        news_section = "\n\n📰 اخبار اخیر:\n"
        for n in news[:2]:
            news_section += f"• {n[:80]}\n"

    # ارسال
    if dollar and btc_toman:
        if signal == "BUY":
            msg = (
                f"🟢🟢 سیگنال خرید قوی!\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"📈 MA7: ${ma7}\n"
                f"🟠 BTC: {btc_toman:,.0f} تومان"
                f"{news_section}\n\n"
                f"{WARNING_MSG}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("STRONG BUY")
        elif signal == "SELL":
            msg = (
                f"🔴🔴 سیگنال فروش قوی!\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"📉 MA7: ${ma7}\n"
                f"🟠 BTC: {btc_toman:,.0f} تومان"
                f"{news_section}\n\n"
                f"{WARNING_MSG}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("STRONG SELL")
        elif signal == "BUY_SIMPLE":
            msg = (
                f"🟢 سیگنال خرید (ساده)\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"🟠 BTC: {btc_toman:,.0f} تومان"
                f"{news_section}\n\n"
                f"{WARNING_MSG}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("SIMPLE BUY")
        elif signal == "SELL_SIMPLE":
            msg = (
                f"🔴 سیگنال فروش (ساده)\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"🟠 BTC: {btc_toman:,.0f} تومان"
                f"{news_section}\n\n"
                f"{WARNING_MSG}"
            )
            await bot.send_message(CHAT_ID, msg)
            print("SIMPLE SELL")
        else:
            print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")

asyncio.run(main())
