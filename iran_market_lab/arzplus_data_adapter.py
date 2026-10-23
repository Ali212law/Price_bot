import requests
import json
import os
import time
from datetime import datetime, timezone

ARZPLUS_API = "https://api.arzplus.net/api/v1/market/tradingview/ohlcv"
DATA_DIR = "data"

# نگاشت نمادهای استاندارد به ارزپلاس
SYMBOL_MAP = {
    "BTCTMN": "BTCIRT",
    "ETHTMN": "ETHIRT",
    "SOLTMN": "SOLIRT",
    "XRPTMN": "XRPIRT",
    "ADATMN": "ADAIRT",
    "DOGETMN": "DOGEIRT",
    "BNBTMN": "BNBIRT",
    "TRXTMN": "TRXIRT",
    "LINKTMN": "LINKIRT",
    "AVAXTMN": "AVAXIRT",
    "DOTTMN": "DOTIRT"
}

def fetch_arzplus_klines(symbol, resolution="240", days=730):
    """Fetch 4H klines directly using tradingview standard."""
    now = int(time.time())
    start = now - (days * 24 * 3600)
    
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": start,
        "to": now
    }
    
    try:
        r = requests.get(ARZPLUS_API, params=params, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                candles = []
                for k in data:
                    # ارزپلاس از استاندارد tradingview استفاده می‌کند: time, open, high, low, close, volume
                    candles.append({
                        "t": int(k["time"] / 1000),  # تبدیل به ثانیه
                        "o": float(k["open"]),
                        "h": float(k["high"]),
                        "l": float(k["low"]),
                        "c": float(k["close"]),
                        "v": float(k["volume"])
                    })
                return candles
            else:
                print(f"  Invalid response format for {symbol}")
                return []
        else:
            print(f"  HTTP {r.status_code} for {symbol}: {r.text[:100]}")
            return []
    except Exception as e:
        print(f"  Error for {symbol}: {e}")
        return []

def save_to_json(wallex_symbol, candles):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{wallex_symbol}_4h.json"
    with open(filename, 'w') as f:
        json.dump(candles, f, indent=2)
    return filename

def main():
    print("=== Downloading 4H Data from Arzplus ===\n")
    success = []
    failed = []
    
    for wallex_symbol, arzplus_symbol in SYMBOL_MAP.items():
        print(f"--- {wallex_symbol} ({arzplus_symbol}) ---")
        candles = fetch_arzplus_klines(arzplus_symbol, resolution="240", days=730)
        
        if candles:
            filename = save_to_json(wallex_symbol, candles)
            print(f"  ✅ Saved {len(candles)} candles to {filename}")
            success.append(wallex_symbol)
        else:
            print(f"  ❌ Failed for {wallex_symbol}")
            failed.append(wallex_symbol)
        time.sleep(0.5) # جلوگیری از Rate Limit
    
    print(f"\n=== Summary ===")
    print(f"✅ Success: {len(success)}/{len(SYMBOL_MAP)}")
    print(f"❌ Failed:  {len(failed)}")
    if failed:
        print(f"   Failed symbols: {', '.join(failed)}")

if __name__ == "__main__":
    main()
