#!/usr/bin/env python3
"""
binance_data_collector.py — Fetching Global Market Data (OKX Pagination)
- Fetches ~90 days of 1h data for BTC, ETH, SOL, XRP using OKX API.
- Bypasses geo-blocking.
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
TARGET_CANDLES = 2160 # Approx 90 days of 1H data

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

def fetch_okx_klines_paginated(symbol):
    instId = symbol.replace("USDT", "-USDT")
    all_candles = []
    current_time = int(time.time() * 1000) # Start from now
    
    while len(all_candles) < TARGET_CANDLES:
        # Using history-candles endpoint for older data
        url = f"https://www.okx.com/api/v5/market/history-candles?instId={instId}&bar=1H&limit=100&before={current_time}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == "0" and data.get("data"):
                    result = data.get("data", [])
                    if not result: break
                    
                    for k in result:
                        all_candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])})
                    
                    # Update current_time to the oldest timestamp fetched so far
                    current_time = int(result[-1][0])
                else:
                    print(f"  [OKX API Error] {data}")
                    break
            else:
                print(f"  [HTTP Error] {r.status_code}")
                break
        except Exception as e:
            print(f"  [Fetch Error] {e}")
            break
            
        time.sleep(0.2) # Rate limit prevention

    # Remove duplicates and sort chronologically (oldest to newest)
    seen = set()
    unique_candles = []
    for c in all_candles:
        if c["t"] not in seen:
            seen.add(c["t"])
            unique_candles.append(c)
            
    unique_candles.sort(key=lambda x: x["t"])
    return unique_candles

def main():
    print(f"=== Fetching Global Data (OKX) ({datetime.now(timezone.utc).isoformat()}) ===")
    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, dict): history = {}

    success_count = 0
    for symbol in ASSETS:
        print(f"Fetching {symbol} (Target: {TARGET_CANDLES} candles)...")
        candles = fetch_okx_klines_paginated(symbol)
        
        if candles:
            history[symbol] = candles
            print(f"  -> Saved {len(candles)} candles.")
            success_count += 1
        else:
            print(f"  -> Failed to fetch {symbol}.")
            
    if success_count > 0:
        if save_to_github(HISTORY_FILE, history, sha):
            print("Data saved to GitHub successfully.")
    else:
        print("All fetches failed. Nothing to save.")

if __name__ == "__main__":
    main()
