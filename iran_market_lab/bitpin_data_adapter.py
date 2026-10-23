import requests
import json
import os
import time
from datetime import datetime, timezone

BITPIN_API = "https://api.bitpin.org/api/v1/mth/klines"
DATA_DIR = "data_bitpin"

# ۱۱ ارز هدف
SYMBOLS = [
    "BTCTMN", "ETHTMN", "SOLTMN", "XRPTMN", "ADATMN", 
    "DOGETMN", "BNBTMN", "TRXTMN", "LINKTMN", "AVAXTMN", "DOTTMN"
]


def fetch_bitpin_klines(symbol, resolution="240", days=730):
    """Fetch klines from Bitpin API."""
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600 # دریافت ۱۴ روزه برای جلوگیری از محدودیت API
    candles = []
    current = start
    max_retries = 3
    
    while current < now:
        to_ts = min(current + chunk, now)
        # فرمت فراخوانی API بیت‌پین
        url = f"{BITPIN_API}/{symbol}/?resolution={resolution}&from={current}&to={to_ts}"
        
        for attempt in range(max_retries):
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        for k in data:
                            candles.append({
                                "t": int(k[0]),
                                "o": float(k[1]),
                                "h": float(k[2]),
                                "l": float(k[3]),
                                "c": float(k[4]),
                                "v": float(k[5]) if len(k) > 5 else 0.0
                            })
                        break
                    else:
                        print(f"  Status: {data}")
                        break
                elif r.status_code == 404:
                    print(f"  Symbol {symbol} not found on Bitpin.")
                    return []
                else:
                    print(f"  HTTP {r.status_code} (retry {attempt+1}/{max_retries})")
                    time.sleep(2)
            except Exception as e:
                print(f"  Error (retry {attempt+1}/{max_retries}): {e}")
                time.sleep(2)
        
        current = to_ts
        time.sleep(0.5)
    
    # حذف تکراری‌ها و مرتب‌سازی
    unique = {c['t']: c for c in candles}
    return sorted(unique.values(), key=lambda x: x['t'])


def save_to_json(symbol, candles):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{symbol}_4h.json"
    with open(filename, 'w') as f:
        json.dump(candles, f, indent=2)
    return filename


def print_stats(symbol, candles):
    if not candles:
        print(f"  ❌ No data for {symbol}")
        return False
    
    first_dt = datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc)
    last_dt = datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc)
    print(f"  ✅ Total: {len(candles)} candles")
    print(f"  📅 Range: {first_dt.strftime('%Y-%m-%d')} to {last_dt.strftime('%Y-%m-%d')}")
    print(f"  💰 First: {candles[0]['c']:,.0f} -> Last: {candles[-1]['c']:,.0f}")
    return True


def main():
    print("=== Downloading Data from Bitpin ===\n")
    
    success = []
    failed = []
    
    for symbol in SYMBOLS:
        print(f"--- {symbol} ---")
        candles = fetch_bitpin_klines(symbol, resolution="240", days=730)
        
        if print_stats(symbol, candles):
            filename = save_to_json(symbol, candles)
            print(f"  💾 Saved: {filename}")
            success.append(symbol)
        else:
            failed.append(symbol)
        print()
    
    print(f"=== Summary ===")
    print(f"✅ Success: {len(success)}")
    print(f"❌ Failed:  {len(failed)}")


if __name__ == "__main__":
    main()
