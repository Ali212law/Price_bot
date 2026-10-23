import requests
import json
import os
import time
from datetime import datetime, timezone

WALLEX_API = "https://api.wallex.ir/v1/udf/history"
DATA_DIR = "data"
NEW_SYMBOLS = ["SOLTMN", "XRPTMN", "ADATMN", "DOGETMN"]


def fetch_wallex_klines(symbol, resolution="240", days=730):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
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
                    time.sleep(2)
            except Exception as e:
                print(f"  Error (retry {attempt+1}/{max_retries}): {e}")
                time.sleep(2)
        
        current = to_ts
        time.sleep(0.5)
    
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
        print(f"  No data for {symbol}")
        return False
    first_dt = datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc)
    last_dt = datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc)
    print(f"  Total: {len(candles)} candles")
    print(f"  Range: {first_dt.strftime('%Y-%m-%d')} to {last_dt.strftime('%Y-%m-%d')}")
    print(f"  First: {candles[0]['c']:,.0f} -> Last: {candles[-1]['c']:,.0f}")
    return True


def main():
    print("=== Downloading New Assets from Wallex ===\n")
    success_count = 0
    for symbol in NEW_SYMBOLS:
        print(f"--- {symbol} ---")
        candles = fetch_wallex_klines(symbol, resolution="240", days=730)
        if print_stats(symbol, candles):
            filename = save_to_json(symbol, candles)
            print(f"  Saved: {filename}")
            success_count += 1
        print()
    print(f"=== Done === {success_count}/{len(NEW_SYMBOLS)} assets downloaded")


if __name__ == "__main__":
    main()
