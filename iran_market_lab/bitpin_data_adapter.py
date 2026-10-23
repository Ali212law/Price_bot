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
    candles = []
    current = start
    max_retries = 3
    
    while current < now:
        to_ts = min(current + chunk, now)
        params = {
            "symbol": bitpin_symbol,
            "resolution": resolution,
            "from": current,
            "to": to_ts
        }
        
        for attempt in range(max_retries):
            try:
                r = requests.get(BITPIN_API, params=params, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0:
                        for k in data:
                            candles.append({
                                "t": int(k["ts"]),  # FIX: زمان به ثانیه (بدون ضرب در 1000)
                                "o": float(k["open"]),
                                "h": float(k["high"]),
                                "l": float(k["low"]),
                                "c": float(k["close"]),
                                "v": float(k["volume"])
                            })
                        break
                    else:
                        break
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)
        
        current = to_ts
        time.sleep(0.2)
    
    unique = {c['t']: c for c in candles}
    return sorted(unique.values(), key=lambda x: x['t'])


def resample_to_4h(candles):
    """FIX: تبدیل داده‌های زیر ۴ ساعته (مثل ۳۰ دقیقه) به ۴ ساعته"""
    if not candles: return []
    resampled = []
    current_group = []
    current_ts = None
    
    for c in candles:
        bucket_ts = (c["t"] // 14400) * 14400  # 14400 ثانیه = 4 ساعت
        if current_ts is None:
            current_ts = bucket_ts
        
        if bucket_ts == current_ts:
            current_group.append(c)
        else:
            if current_group:
                resampled.append({
                    "t": current_group[0]["t"],
                    "o": current_group[0]["o"],
                    "h": max(x["h"] for x in current_group),
                    "l": min(x["l"] for x in current_group),
                    "c": current_group[-1]["c"],
                    "v": sum(x["v"] for x in current_group)
                })
            current_group = [c]
            current_ts = bucket_ts
            
    if current_group:
        resampled.append({
            "t": current_group[0]["t"],
            "o": current_group[0]["o"],
            "h": max(x["h"] for x in current_group),
            "l": min(x["l"] for x in current_group),
            "c": current_group[-1]["c"],
            "v": sum(x["v"] for x in current_group)
        })
    return resampled


def save_to_json(wallex_symbol, candles):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{wallex_symbol}_4h.json"
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
    print("=== Downloading Data from Bitpin (Overwriting Wallex Data) ===\n")
    success = []
    failed = []
    
    for wallex_symbol, bitpin_symbol in SYMBOL_MAP.items():
        print(f"--- {wallex_symbol} ({bitpin_symbol}) ---")
        candles = fetch_bitpin_klines(bitpin_symbol, resolution="240", days=730)
        
        # اگر تعداد کندل‌ها بسیار زیاد بود (یعنی API تایم‌فریم ۴ ساعته را نادیده گرفته)
        if len(candles) > 5000:
            print(f"  ⚠️ Got {len(candles)} candles, resampling to 4H...")
            candles = resample_to_4h(candles)
        
        if print_stats(wallex_symbol, candles):
            filename = save_to_json(wallex_symbol, candles)
            print(f"  💾 Saved: {filename}")
            success.append(wallex_symbol)
        else:
            failed.append(wallex_symbol)
        print()
    
    print(f"=== Summary ===")
    print(f"✅ Success: {len(success)}")
    print(f"❌ Failed:  {len(failed)}")


if __name__ == "__main__":
    main()
