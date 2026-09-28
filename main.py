import requests
import asyncio
import json
import os
import base64
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["976125210:_cbeFJmOWtW5ZPrw0Lm-bskEI_kpfdb-amY"]
CHAT_ID = os.environ["2000522384"]
ABAN_API_KEY = os.environ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjY0MjQyIiwiaWF0IjoxNzkwNTQzODE0LjczMTc5MjIsImV4cCI6MTgyMjA3OTgxNCwic2Vzc2lvbl9pZCI6ImVkZjM5MTJlLWY5ODUtNDE2Ny1hM2M3LTQ4MmE4Yjk0M2QzZiIsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJ0eXBlIjoiQVBJIiwiYW1yIjpbXSwiYXV0aF90aW1lIjpbXSwibWV0YWRhdGEiOltdLCJyZXF1aXJlZF9sYXllcnMiOnt9LCJhY3IiOiJhYWwwIn0.JNRokA4QztR13Lrbbw7iSpglUcOjUrwbOMOLFwRgraE"]
GH_TOKEN = os.environ["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"]
GH_REPO = "Ali212law/Price_bot"
HISTORY_FILE = "dollar_history.json"
SIGNAL_THRESHOLD = 2.0

bot = Client(976125210:_cbeFJmOWtW5ZPrw0Lm-bskEI_kpfdb-amY)

def load_history_from_github():
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{HISTORY_FILE}"
        headers = {"Authorization": f"token {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}"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            history_data = json.loads(content)
            return [(datetime.fromisoformat(t), p) for t, p in history_data], data["sha"]
        else:
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
        headers = {"Authorization": f"token {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}"}
        
        payload = {
            "message": "Update history",
            "content": content_b64,
        }
        if sha:
            payload["sha"] = sha
        
        r = requests.put(url, headers=headers, json=payload, timeout=10)
        if r.status_code in [200, 201]:
            print("HISTORY SAVED")
        else:
            print(f"SAVE ERROR: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"SAVE ERROR: {e}")

async def main():
    dollar = None
    btc = None
    
    # دریافت قیمت دلار
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
    
    # خوندن تاریخچه از GitHub
    history, sha = load_history_from_github()
    print(f"LOADED: {len(history)} records")
    
    now = datetime.now()
    
    if dollar:
        history.append((now, dollar))
        history[:] = [(t, p) for t, p in history 
                      if now - t < timedelta(hours=24)]
        save_history_to_github(history, sha)
    
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
