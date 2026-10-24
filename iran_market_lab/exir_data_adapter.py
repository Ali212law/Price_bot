import requests
import json
import os
import time
from datetime import datetime, timezone

EXIR_API = "https://api.exir.io/v2/chart"
DATA_DIR = "data_exir"

# نگاشت نمادهای پروژه به نمادهای اکسیر (با فرمت irt)
SYMBOL_MAP = {
    "BTCTMN": "btc-irt", "ETHTMN": "eth-irt", "SOLTMN": "sol-irt",
    "XRPTMN": "xrp-irt", "ADATMN": "ada-irt", "DOGETMN": "doge-irt",
    "BNBTMN": "bnb-irt", "TRXTMN": "trx-irt", "LINKTMN": "link-irt",
    "AVAXTMN": "avax-irt", "DOTTMN": "dot-irt"
}


def fetch_exir_klines(exir_symbol, resolution="240", days=730):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 30 * 24 * 3600 # دریافت ۳۰ روزه در هر درخواست
    candles = []
    current = start
    
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"{EXIR_API}?symbol={exir_symbol}&resolution={resolution}&from={current}&to={to_ts}"
        
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for k in data:
                        # تبدیل زمان ISO به Unix Timestamp
                        dt = datetime.fromisoformat(k["time"].replace("Z", "+00:00"))
                        ts = int(dt.timestamp())
                        candles.append({
                            "t": ts,
                            "o": float(k["open"]),
                            "h": float(k["high"]),
                            "l": float(k["low"]),
                            "c": float(k["close"]),
                            "v": float(k["volume"])
                        })
            else:
                print(f"  HTTP {r.status_code} for {exir_symbol}")
                break
        except Exception as e:
            print(f"  Error: {e}")
            break
            
        current = to_ts
        time.sleep(0.5) # جلوگیری از محدودیت درخواست
    
    # حذف تکراری‌ها و مرتب‌سازی
    unique = {c['t']: c for c in candles}
    return sorted(unique.values(), key=lambda x: x['t'])


def main():
    print("=== Downloading Data from Exir ===\n")
    os.makedirs(DATA_DIR, exist_ok=True)
    
    for proj_symbol, exir_symbol in SYMBOL_MAP.items():
        print(f"--- {proj_symbol} ({exir_symbol}) ---")
        candles = fetch_exir_klines(exir_symbol)
        
        if candles:
            filename = f"{DATA_DIR}/{proj_symbol}_4h.json"
            with open(filename, 'w') as f:
                json.dump(candles, f, indent=2)
            print(f"  ✅ Saved {len(candles)} candles to {filename}")
        else:
            print(f"  ❌ No data found.")
        print()

if __name__ == "__main__":
    main()
