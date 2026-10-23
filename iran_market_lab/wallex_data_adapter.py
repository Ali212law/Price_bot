import requests
import json
import os
import time
from datetime import datetime, timezone

WALLEX_API = "https://api.wallex.ir/v1/udf/history"
DATA_DIR = "data"


def fetch_wallex_klines(symbol, resolution="240", days=730):
    """Fetch klines from Wallex UDF endpoint.
    resolution: "240" = 4h, "60" = 1h, "D" = 1 day
    """
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600  # 14-day chunks
    candles = []
    current = start
    max_retries = 3
    
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"{WALLEX_API}?symbol={symbol}&resolution={resolution}&from={current}&to={to_ts}"
        
        for attempt in range(max_retries):
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if data.get('s') == 'ok':
                        t_list = data.get('t', [])
                        for i in range(len(t_list)):
                            candles.append({
                                "t": int(data['t'][i]),
                                "o": float(data['o'][i]),
                                "h": float(data['h'][i]),
                                "l": float(data['l'][i]),
                                "c": float(data['c'][i]),
                                "v": float(data['v'][i]) if 'v' in data else 0.0
                            })
                        break
                    else:
                        print(f"  Wallex status: {data.get('s')}")
                        break
                else:
                    print(f"  HTTP {r.status_code} (retry {attempt+1}/{max_retries})")
                    time.sleep(2)
            except Exception as e:
                print(f"  Error (retry {attempt+1}/{max_retries}): {e}")
                time.sleep(2)
        
        current = to_ts
        time.sleep(0.5)  # Rate limit
    
    # Deduplicate and sort
    unique = {c['t']: c for c in candles}
    return sorted(unique.values(), key=lambda x: x['t'])


def save_to_json(symbol, candles, resolution="4h"):
    """Save candles to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"{DATA_DIR}/{symbol}_{resolution}.json"
    with open(filename, 'w') as f:
        json.dump(candles, f, indent=2)
    return filename


def print_stats(symbol, candles):
    """Print summary statistics."""
    if not candles:
        print(f"  ❌ No data for {symbol}")
        return
    
    first_dt = datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc)
    last_dt = datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc)
    print(f"  ✅ Total: {len(candles)} candles")
    print(f"  📅 Range: {first_dt.strftime('%Y-%m-%d')} to {last_dt.strftime('%Y-%m-%d')}")
    print(f"  💰 First close: {candles[0]['c']:,.0f}")
    print(f"  💰 Last close: {candles[-1]['c']:,.0f}")
    
    # Check for gaps
    if len(candles) > 1:
        expected_interval = 4 * 3600
        gaps = 0
        for i in range(1, len(candles)):
            if candles[i]['t'] - candles[i-1]['t'] > expected_interval * 1.5:
                gaps += 1
        print(f"  ⚠️ Gaps (>1.5x interval): {gaps}")


def main():
    symbols = ["BTCTMN", "ETHTMN", "USDTTMN"]
    
    print("=== Wallex Data Adapter (4h, 730 days) ===\n")
    
    for symbol in symbols:
        print(f"--- {symbol} ---")
        candles = fetch_wallex_klines(symbol, resolution="240", days=730)
        print_stats(symbol, candles)
        
        if candles:
            filename = save_to_json(symbol, candles)
            print(f"  💾 Saved to: {filename}")
        print()
    
    print("=== Done ===")


if __name__ == "__main__":
    main()
