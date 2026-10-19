#!/usr/bin/env python3
"""
binance_data_collector.py — Fetching Global Market Data (Bybit + OKX Fallback)
"""
import requests
import time
import json
import base64
import os
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
HISTORY_FILE = "global_history.json"
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

# هدر مرورگر برای دور زدن فیلترهای جغرافیایی
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return {}, None
    except: return {}, None

def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"SAVE ERROR: {e}")
        return False

def fetch_bybit_klines(symbol, interval="60", limit=1000):
    url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("retCode") == 0:
                result = data.get("result", {}).get("list", [])
                candles = []
                for k in result:
                    candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])})
                candles.sort(key=lambda x: x["t"])
                return candles
            else:
                print(f"  [Bybit API Error] {data.get('retMsg')}")
    except Exception as e:
        print(f"  [Bybit Fetch Error] {e}")
    return []

def fetch_okx_klines(symbol, limit=300):
    # OKX uses BTC-USDT format
    instId = symbol.replace("USDT", "-USDT")
    url = f"https://www.okx.com/api/v5/market/candles?instId={instId}&bar=1H&limit={limit}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == "0":
                result = data.get("data", [])
                candles = []
                for k in result:
                    candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])})
                candles.sort(key=lambda x: x["t"])
                return candles
    except Exception as e:
        print(f"  [OKX Fetch Error] {e}")
    return []

def main():
    print(f"=== Fetching Global Data ({datetime.now(timezone.utc).isoformat()}) ===")
    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, dict): history = {}

    success_count = 0
    for symbol in ASSETS:
        print(f"Fetching {symbol}...")
        # Try Bybit first
        candles = fetch_bybit_klines(symbol)
        
        # If Bybit fails, try OKX
        if not candles:
            print(f"  -> Bybit failed, trying OKX for {symbol}...")
            candles = fetch_okx_klines(symbol)
            
        if candles:
            history[symbol] = candles
            print(f"  -> Saved {len(candles)} candles.")
            success_count += 1
        else:
            print(f"  -> Failed to fetch {symbol} from both sources.")
        time.sleep(1) # Polite delay

    if success_count > 0:
        if save_to_github(HISTORY_FILE, history, sha):
            print("Data saved to GitHub successfully.")
    else:
        print("All fetches failed. Nothing to save.")

if __name__ == "__main__":
    main()
