#!/usr/bin/env python3
"""
binance_data_collector.py — Fetching Global Market Data (Binance)
- Fetches 90 days of 1h data for BTC, ETH, SOL, XRP.
- Saves to binance_history.json.
"""
import requests
import time
import json
import base64
import os
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
HISTORY_FILE = "binance_history.json"
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

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

def fetch_binance_klines(symbol, interval="1h", limit=1000):
    # Fetching 1000 candles (approx 41 days for 1h)
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            candles = []
            for k in data:
                candles.append({
                    "t": int(k[0]), # Open time
                    "o": float(k[1]),
                    "h": float(k[2]),
                    "l": float(k[3]),
                    "c": float(k[4]),
                    "v": float(k[5])
                })
            return candles
    except Exception as e:
        print(f"FETCH ERROR ({symbol}): {e}")
    return []

def main():
    print(f"=== Fetching Binance Data ({datetime.now(timezone.utc).isoformat()}) ===")
    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, dict): history = {}

    for symbol in ASSETS:
        print(f"Fetching {symbol}...")
        candles = fetch_binance_klines(symbol, interval="1h", limit=1000)
        if candles:
            history[symbol] = candles
            print(f"  -> Saved {len(candles)} candles.")
        else:
            print(f"  -> Failed to fetch {symbol}.")
        time.sleep(0.5) # Rate limit prevention

    if save_to_github(HISTORY_FILE, history, sha):
        print("Binance data saved to GitHub successfully.")
    else:
        print("Failed to save data.")

if __name__ == "__main__":
    main()
