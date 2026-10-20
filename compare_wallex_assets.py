#!/usr/bin/env python3
# compare_wallex_assets.py — Scans TMN pairs on Wallex for Best Buy & Hold ROI

import requests, time

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ارزهای برتر که احتمالا در والکس وجود دارند
TARGET_BASES = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "LTC", "DOT", "LINK", "AVAX"]

def fetch_wallex_daily(symbol, days=1095): # 3 years
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    current = start
    
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={symbol}&resolution=1D&from={current}&to={to_ts}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    c = float(data['c'][i])
                    if c > 100_000_000_000: c /= 10
                    candles.append({"t": int(data['t'][i]), "c": c})
        except Exception:
            pass
        current = to_ts
        time.sleep(0.3)
        
    unique = {c['t']: c for c in candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

def main():
    results = []
    print("Scanning Wallex TMN pairs for historical Buy & Hold performance...")
    
    for base in TARGET_BASES:
        symbol = f"{base}TMN"
        print(f"Fetching {symbol}...", end="\r")
        data = fetch_wallex_daily(symbol)
        
        if len(data) < 100:
            continue
            
        start_price = data[0]['c']
        end_price = data[-1]['c']
        
        if start_price == 0: continue
        
        roi = ((end_price - start_price) / start_price) * 100
        
        # Max Drawdown calculation
        peak = data[0]['c']
        max_dd = 0.0
        for c in data:
            if c['c'] > peak:
                peak = c['c']
            dd = (peak - c['c']) / peak * 100
            if dd > max_dd:
                max_dd = dd
                
        results.append({
            "symbol": symbol,
            "start": start_price,
            "end": end_price,
            "roi": roi,
            "max_dd": max_dd,
            "days": len(data)
        })
        
    results.sort(key=lambda x: x["roi"], reverse=True)
    
    print("\n\n=== Wallex Buy & Hold Performance (Max Available History) ===")
    print(f"{'Symbol':<10} | {'ROI (%)':<12} | {'MaxDD (%)':<12} | {'Days':<6}")
    print("-" * 50)
    
    for r in results:
        print(f"{r['symbol']:<10} | {r['roi']:>+10.1f}% | {r['max_dd']:>10.1f}% | {r['days']:<6}")

if __name__ == "__main__":
    main()
