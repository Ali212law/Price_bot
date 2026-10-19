#!/usr/bin/env python3
# fetch_deep_data.py — Fetch 3 Years of 4H Data for Top 10 Assets

import requests, json, time, os

HEADERS = {"User-Agent": "Mozilla/5.0"}
TARGET_CANDLES = 6800 # ~3 Years of 4H
INTERVAL = "4h"
OUTPUT_FILE = "deep_history_4h.json"
STABLECOINS = ["USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "BUSD", "AEUR", "USD1"]

def get_top_10_assets():
    print("Fetching top 10 assets by volume...")
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    r = requests.get(url, headers=HEADERS, timeout=20)
    data = r.json()
    
    usdt_pairs = []
    for item in data:
        symbol = item["symbol"]
        if symbol.endswith("USDT"):
            base = symbol.replace("USDT", "")
            if base not in STABLECOINS:
                vol = float(item["quoteVolume"])
                usdt_pairs.append({"symbol": symbol, "volume": vol})
                
    usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
    top_10 = [x["symbol"] for x in usdt_pairs[:10]]
    print(f"Top 10: {top_10}")
    return top_10

def fetch_binance_vision(symbol, interval="4h", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    
    while len(all_candles) < TARGET_CANDLES:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&endTime={end_time}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])})
                end_time = data[0][0] - 1
                print(f"  Fetched {len(all_candles)}/{TARGET_CANDLES} candles...", end="\r")
            else: break
        except Exception as e:
            print(f"\n  Error: {e}")
            break
        time.sleep(0.3)
        
    print() # New line after progress
    seen, unique = set(), []
    for c in all_candles:
        if c["t"] not in seen:
            seen.add(c["t"]); unique.append(c)
    unique.sort(key=lambda x: x["t"])
    return unique[-TARGET_CANDLES:]

def main():
    top_10 = get_top_10_assets()
    deep_data = {}
    
    for sym in top_10:
        print(f"Fetching {sym} ({INTERVAL})...")
        candles = fetch_binance_vision(sym)
        if len(candles) > 5000:
            deep_data[sym] = candles
            print(f"  -> Saved {len(candles)} candles.")
        else:
            print(f"  -> Not enough data ({len(candles)}), skipping.")
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(deep_data, f, ensure_ascii=False)
    print(f"\nSaved {len(deep_data)} assets to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
