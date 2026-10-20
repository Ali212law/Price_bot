#!/usr/bin/env python3
# backtest_m14_grid.py — Simulation of Grid Strategies on Binance 5m Data
# Assets: SOL, DOGE, AVAX | Spacing: 2.5x ATR | Maker Fee: 0.02% (Round-trip 0.04%)

import requests, time

SYMBOLS = ["SOLUSDT", "DOGEUSDT", "AVAXUSDT"]
INTERVAL = "5m"
DAYS = 30
MAKER_FEE = 0.02 # 0.02% per side (0.04% round-trip)
GRID_MULTIPLIER = 2.5 # Grid spacing = 2.5 * ATR

def fetch_binance_vision(symbol, interval="5m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = DAYS * 24 * 12 # 5m candles in 30 days = 8640
    
    while len(all_candles) < target:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&endTime={end_time}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]), 
                        "l": float(k[3]), "c": float(k[4]), "v": float(k[5])
                    })
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.2)
    
    unique = {c['t']: c for c in all_candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

def calc_atr(candles, period=14):
    n = len(candles)
    atr = [0.0] * n
    if n <= period: return atr
    trs = []
    for i in range(1, n):
        trs.append(max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - candles[i-1]['c']), abs(candles[i]['l'] - candles[i-1]['c'])))
        if i >= period:
            atr[i] = sum(trs[-period:]) / period
    return atr

def main():
    print("=== M14-Grid Viability Test (High Volatility Assets) ===")
    print(f"Parameters: Grid Spacing = {GRID_MULTIPLIER}x ATR | Fee = {MAKER_FEE*2}% round-trip\n")
    
    for symbol in SYMBOLS:
        print(f"Fetching {symbol} {INTERVAL} data for {DAYS} days...")
        candles = fetch_binance_vision(symbol, INTERVAL)
        print(f"Fetched {len(candles)} candles.")
        
        if len(candles) < 1000:
            print("Not enough data. Skipping.\n")
            continue

        atr = calc_atr(candles, 14)
        current_price = candles[-1]['c']
        
        # Calculate average ATR% over the last 1000 candles
        recent_atr = atr[-1000:]
        avg_atr = sum(recent_atr) / len(recent_atr)
        avg_atr_pct = (avg_atr / current_price) * 100
        
        # Grid spacing percentage
        grid_spacing_pct = avg_atr_pct * GRID_MULTIPLIER
        
        # Profit per grid after round-trip fees
        net_profit_pct = grid_spacing_pct - (MAKER_FEE * 2)
        
        print(f"Average ATR(14): {avg_atr_pct:.3f}%")
        print(f"Grid Spacing (2.5x ATR): {grid_spacing_pct:.3f}%")
        print(f"Net Profit per Grid (after 0.04% fee): {net_profit_pct:+.3f}%")
        
        if net_profit_pct > 0.1:
            print(">> VERDICT: VIABLE (Net profit is healthy)")
        elif net_profit_pct > 0:
            print(">> VERDICT: MARGINAL (Very tight, sensitive to slippage)")
        else:
            print(">> VERDICT: NOT VIABLE (Fees eat the spacing)")
        
        print("-" * 50)

if __name__ == "__main__":
    main()
