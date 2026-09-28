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
TRADES_FILE = "trades_history.json"
SIGNAL_THRESHOLD = 2.0
TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False") == "True"

# ===== تنظیمات معامله =====
MAX_TRADE_TOMAN = 50000
MAX_DAILY_TRADES = 3
MAX_DAILY_LOSS_TOMAN = 50000
STOP_LOSS_PERCENT = 1
TAKE_PROFIT_PERCENT = 2

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

# ===== مدیریت معاملات =====

def get_today_trades(trades):
    today = datetime.now().date().isoformat()
    return [t for t in trades if t.get("date") == today]

def can_trade_today(trades):
    today_trades = get_today_trades(trades)
    if len(today_trades) >= MAX_DAILY_TRADES:
        print(f"DAILY TRADES LIMIT REACHED: {len(today_trades)}/{MAX_DAILY_TRADES}")
        return False
    return True

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

    # تاریخچه دلار
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

    # تاریخچه معاملات
    trades_data, trades_sha = load_from_github(TRADES_FILE)
    trades = trades_data if trades_data else []
    print(f"TRADES: {len(trades)} total")

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

    # بخش اخبار
    news_section = ""
    if news:
        news_section = "\n\n📰 اخبار اخیر:\n"
        for n in news[:2]:
            news_section += f"• {n[:80]}\n"

    # ===== معامله خودکار =====
    if dollar and btc_toman and signal:
        # فقط سیگنال‌های قوی معامله می‌شن
        if signal in ["BUY", "SELL"]:
            if not TRADING_ENABLED:
                print("TRADING DISABLED - SIGNAL ONLY")
                msg = (
                    f"🟢 سیگنال {signal} قوی!\n\n"
                    f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                    f"📊 RSI: {rsi}\n"
                    f"🟠 BTC: {btc_toman:,.0f} تومان"
                    f"{news_section}\n\n"
                    f"⚠️ معامله غیرفعاله (TRADING_ENABLED=False)\n"
                    f"{WARNING_MSG}"
                )
                await bot.send_message(CHAT_ID, msg)
            elif not can_trade_today(trades):
                print("DAILY LIMIT - SKIP")
                await bot.send_message(
                    CHAT_ID,
                    f"⚠️ سقف معاملات روزانه پر شده ({MAX_DAILY_TRADES} معامله)"
                )
            else:
                # معامله خودکار
                side = "buy" if signal == "BUY" else "sell"
                print(f"AUTO TRADING: {side}")
                result = place_order(side, btc_toman)

                if result:
                    # ذخیره معامله
                    trade = {
                        "date": now.date().isoformat(),
                        "time": now.isoformat(),
                        "side": side,
                        "price": btc_toman,
                        "amount_toman": MAX_TRADE_TOMAN,
                        "signal": signal,
                        "rsi": rsi,
                        "dollar": dollar,
                        "status": "open"
                    }
                    trades.append(trade)
                    save_to_github(TRADES_FILE, trades, trades_sha)

                    msg = (
                        f"✅ معامله {side} انجام شد!\n\n"
                        f"💰 قیمت: {btc_toman:,.0f} تومان\n"
                        f"💵 مبلغ: {MAX_TRADE_TOMAN:,.0f} تومان\n"
                        f"📊 RSI: {rsi}\n"
                        f"🟠 دلار: {dollar:,.0f}"
                        f"{news_section}\n\n"
                        f"📈 حد ضرر: {STOP_LOSS_PERCENT}٪\n"
                        f"📈 حد سود: {TAKE_PROFIT_PERCENT}٪\n\n"
                        f"{WARNING_MSG}"
                    )
                    await bot.send_message(CHAT_ID, msg)
                    print(f"TRADE EXECUTED: {side}")
                else:
                    await bot.send_message(CHAT_ID, "❌ معامله انجام نشد (خطای API)")
                    print("TRADE FAILED")
        else:
            # سیگنال ساده - فقط گزارش
            emoji = "🟢" if "BUY" in signal else "🔴"
            signal_text = "خرید" if "BUY" in signal else "فروش"
            msg = (
                f"{emoji} سیگنال {signal_text} ساده\n\n"
                f"💰 دلار: {dollar:,.0f} ({dollar_change:+.2f}٪)\n"
                f"📊 RSI: {rsi}\n"
                f"🟠 BTC: {btc_toman:,.0f} تومان"
                f"{news_section}\n\n"
                f"ℹ️ سیگنال ساده - معامله انجام نمی‌شه\n"
                f"{WARNING_MSG}"
            )
            await bot.send_message(CHAT_ID, msg)
            print(f"SIMPLE SIGNAL: {signal}")
    else:
        print(f"NO SIGNAL - RSI={rsi} - CHANGE={dollar_change:+.2f}%")

asyncio.run(main())
