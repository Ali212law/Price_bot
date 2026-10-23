import requests
import json
import os
import time
from datetime import datetime, timezone

BITPIN_API = "https://api.bitpin.org/api/v1/mkt/candles/"
DATA_DIR = "data"
SYMBOL_MAP = {
    "BTCTMN": "BTC_IRT", "ETHTMN": "ETH_IRT", "SOLTMN": "SOL_IRT",
    "XRPTMN": "XRP_IRT", "ADATMN": "ADA_IRT", "DOGETMN": "DOGE_IRT",
    "BNBTMN": "BNB_IRT", "TRXTMN": "TRX_IRT", "LINKTMN": "LINK_IRT",
    "AVAXTMN": "AVAX_IRT", "DOTTMN": "DOT_IRT"
}

def fetch_bitpin_klines(bitpin_symbol, resolution="240", days=730):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 30 * 24 * 3600
    candles, current = [], start
    
    while current < now:
        to_ts = min(current + chunk, now)
        params = {"symbol": bitpin_symbol, "resolution": resolution, "from": current, "to": to_ts}
        for _ in range(3):
            try:
                r = requests.get(BITPIN_API, params=params, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0:
                        for k in data:
                            candles.append({"t": int(k["ts"]), "o": float(k["open"]), "h": float(k["high"]), "l": float(k["low"]), "c": float(k["close"]), "v": float(k["volume"])})
                        break
                    else: break
                else: time.sleep(2)
            except: time.sleep(2)
        current = to_ts
        time.sleep(0.2)
    
    unique = {c['t']: c for c in candles}
    return sorted(unique.values(), key=lambda x: x['t'])

def resample_to_4h(candles):
    if not candles: return []
    resampled, current_group, current_ts = [], [], None
    for c in candles:
        bucket_ts = (c["t"] // 14400) * 14400
        if current_ts is None: current_ts = bucket_ts
        if bucket_ts == current_ts: current_group.append(c)
        else:
            if current_group:
                resampled.append({"t": current_group[0]["t"], "o": current_group[0]["o"], "h": max(x["h"] for x in current_group), "l": min(x["l"] for x in current_group), "c": current_group[-1]["c"], "v": sum(x["v"] for x in current_group)})
            current_group, current_ts = [c], bucket_ts
    if current_group:
        resampled.append({"t": current_group[0]["t"], "o": current_group[0]["o"], "h": max(x["h"] for x in current_group), "l": min(x["l"] for x in current_group), "c": current_group[-1]["c"], "v": sum(x["v"] for x in current_group)})
    return resampled

def save_to_json(wallex_symbol, candles):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{wallex_symbol}_4h.json"
    with open(filename, 'w') as f: json.dump(candles, f, indent=2)

def main():
    print("=== Downloading Data from Bitpin ===\n")
    for wallex_symbol, bitpin_symbol in SYMBOL_MAP.items():
        print(f"--- {wallex_symbol} ---")
        candles = fetch_bitpin_klines(bitpin_symbol, resolution="240", days=730)
        if len(candles) > 5000:
            print(f"  Got {len(candles)} candles (30m), resampling to 4H...")
            candles = resample_to_4h(candles)
        if candles:
            save_to_json(wallex_symbol, candles)
            print(f"  Saved {len(candles)} candles to data/{wallex_symbol}_4h.json")
        else:
            print(f"  No data for {wallex_symbol}")
        print()

if __name__ == "__main__":
    main()
