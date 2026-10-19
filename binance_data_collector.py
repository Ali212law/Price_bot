#!/usr/bin/env python3
"""
global_data_collector.py — Fetching Global Market Data (Bybit)
- Fetches 90 days of 1h data for BTC, ETH, SOL, XRP.
- Saves to global_history.json.
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
    # Bybit V5 API (60 = 1 hour)
    url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("retCode") == 0:
                result = data.get("result", {}).get("list", [])
                candles = []
                for k in result:
                    candles.append({
                        "t": int(k[0]), # Open time
                        "o": float(k[1]),
                        "h": float(k[2]),
                        "l": float(k[3]),
                        "c": float(k[4]),
                        "v": float(k[5])
                    })
                candles.sort(key=lambda x: x["t"]) # Bybit returns newest first
                return candles
    except Exception as e:
        print(f"FETCH ERROR ({symbol}): {e}")
    return []

def main():
    print(f"=== Fetching Global Data ({datetime.now(timezone.utc).isoformat()}) ===")
    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, dict): history = {}

    success_count = 0
    for symbol in ASSETS:
        print(f"Fetching {symbol}...")
        candles = fetch_bybit_klines(symbol, interval="60", limit=1000)
        if candles:
            history[symbol] = candles
            print(f"  -> Saved {len(candles)} candles.")
            success_count += 1
        else:
            print(f"  -> Failed to fetch {symbol}.")
        time.sleep(0.5)

    if success_count > 0:
        if save_to_github(HISTORY_FILE, history, sha):
            print("Data saved to GitHub successfully.")
        else:
            print("Failed to save data to GitHub.")
    else:
        print("All fetches failed. Nothing to save.")

if __name__ == "__main__":
    main()
