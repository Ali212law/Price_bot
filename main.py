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
PENDING_FILE = "pending_signal.json"
SIGNAL_THRESHOLD = 2.0
TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False") == "True"

# ===== تنظیمات معامله =====
MAX_TRADE_TOMAN = 50000
MAX_DAILY_TRADES = 3
MAX_DAILY_LOSS_TOMAN = 50000
STOP_LOSS_PERCENT = 1
TAKE_PROFIT_PERCENT = 2

SIGNAL_EXPIRY_MINUTES = 30
MAX_PRICE_DRIFT_PERCENT = 1.0

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
        titles = [t for t in titles if "Cointelegraph" not in t and len(t) > 20]
        return titles[:3]
    except Exception as e:
        print(f"NEWS ERROR: {e}")
        return []

# ===== ذخیره‌سازی در GitHub =====

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

def delete_from_github(filename):
    try:
        data, sha = load_from_github(filename)
        if not sha:
            return
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        payload = {"message": f"Delete {filename}", "sha": sha}
        r = requests.delete(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"DELETED: {filename}")
    except Exception as e:
        print(f"DELETE ERROR ({filename}): {e}")

# ===== معامله در آبان‌تتر =====

def place_order(side, btc_toman_price, amount_toman=MAX_TRADE_TOMAN):
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
            "price": str(int(btc_toman_price)),
            "volume": str(btc_volume)
        }
        print(f"PLACING ORDER: {side} - {btc_volume} BTC @ {btc_toman_price}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        result = r.json()
        print(f"ORDER RESULT: {result}")
        return result
    except Exception as e:
        print(f"ORDER ERROR: {e}")
        return None

# ===== دریافت پیام‌های جدید از بله =====

def get_updates(offset=None):
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/getUpdates"
        params = {"timeout": 0}
        if offset:
            params["offset"] = offset
        r = requests.get(url, params=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"GET UPDATES ERROR: {e}")
        return None

# ===== منطق اصلی =====

async def main():
    dollar = None
    btc_toman = None

    try:
        r = requests.get(
            "https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl",
            timeout=10
        )
        dollar = float(r.json()["data"][0][1].replace(",", ""))
        print(f"DOLLAR: {dollar}")
    except Exception as e:
        print(f"DOLLAR ERROR: {e}")

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

    # چک تأیید کاربر
    pending_data, pending_sha = load_from_github(PENDING_FILE)

    if pending_data:
        print(f"PENDING SIGNAL FOUND: {pending_data.get('signal')}")

        expiry = datetime.fromisoformat(pending_data["expiry"])
        if datetime.now() > expiry:
            print("SIGNAL EXPIRED")
            await bot.send_message(CHAT_ID, "⏰ سیگنال منقضی شد (بیش از ۳۰ دقیقه گذشته)، معامله لغو شد.")
            delete_from_github(PENDING_FILE)
        else:
            ref_price = pending_data["btc_toman"]
            if btc_toman:
                drift = abs(btc_toman - ref_price) / ref_price * 100
                print(f"PRICE DRIFT: {drift:.2f}%")

                if drift > MAX_PRICE_DRIFT_PERCENT:
                    print("PRICE DRIFT TOO HIGH - CANCEL")
                    await bot.send_message(
                        CHAT_ID,
                        f"⚠️ قیمت {drift:.1f}٪ تغییر کرده (بیش از حد مجاز)، معامله لغو شد."
                    )
                    delete_from_github(PENDING_FILE)
                else:
                    updates = get_updates()
                    if updates and "result" in updates:
                        for update in updates["result"]:
                            if "message" in update and "text" in update["message"]:
                                text = update["message"]["text"].strip().upper()
                                if text in ["BUY", "SELL"]:
                                    side = text.lower()
                                    if TRADING_ENABLED:
                                        print(f"USER CONFIRMED: {side}")
                                        result = place_order(side, btc_toman)
                                        if result:
                                            msg = (
                                                f"✅ سفارش {side} ثبت شد!\n\n"
                                                f"قیمت: {btc_toman:,.0f} تومان\n"
                                                f"مبلغ: {MAX_TRADE_TOMAN:,.0f} تومان"
                                            )
                                            await bot.send_message(CHAT_ID, msg)
                                        delete_from_github(PENDING_FILE)
                                    else:
                                        print("TRADING DISABLED")
                                        await bot.send_message(
                                            CHAT_ID,
                                            "⚠️ معامله غیرفعاله (TRADING_ENABLED=False)"
                                        )

    # سیگنال جدید
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

    if dollar and btc_toman and signal and not pending_data:
        signal_data = {
            "signal": signal,
            "btc_toman": btc_toman,
            "dollar": dollar,
            "timestamp": now.isoformat(),
            "expiry": (now + timedelta(minutes=SIGNAL_EXPIRY_MINUTES)).isoformat()
        }
        save_to_github(PENDING_FILE, signal_data, pending_sha)

        emoji = "🟢" if "BUY" in signal else "🔴"
        signal_text = "خرید" if "BUY" in signal else "فروش"
        strength = "قوی" if "_SIMPLE" not in signal else "ساده"

        msg = (
            f"{emoji}{emoji} سیگنال {signal_text} {strength}!\n\n"
            f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
            f"📊 RSI: {rsi}\n"
            f"📈 MA7: ${ma7}\n"
            f"🟠 BTC: {btc_toman:,.0f} تومان"
            f"{news_section}\n\n"
            f"⏰ اعتبار سیگنال: {SIGNAL_EXPIRY_MINUTES} دقیقه\n"
            f"🔐 برای تأیید، بنویس: {signal.split('_')[0]}\n"
            f"⚠️ معامله: {'فعال' if TRADING_ENABLED else 'غیرفعال'}\n\n"
            f"{WARNING_MSG}"
        )
        await bot.send_message(CHAT_ID, msg)
        print(f"SIGNAL SENT: {signal}")
    elif pending_data:
        print("PENDING SIGNAL EXISTS - SKIP NEW SIGNAL")
    else:
        print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")

asyncio.run(main())
