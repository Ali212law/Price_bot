#!/usr/bin/env python3
"""
analyze_holding.py — محاسبه میانگین زمان نگهداری برای سناریوهای SL/TP مختلف
"""
import requests
import time

def fetch_wallex_15m(days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol=BTCTMN&resolution=15&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get('s') == 'ok':
                n = len(data['t'])
                for i in range(n):
                    candles.append({
                        "t": int(data['t'][i]), "o": float(data['o'][i]),
                        "h": float(data['h'][i]), "l": float(data['l'][i]), "c": float(data['c'][i])
                    })
        except Exception:
            pass
        current = to_ts
        time.sleep(0.3)
    candles.sort(key=lambda x: x['t'])
    return candles

def precompute_rsi(closes, period=14):
    rsi_vals = [None] * len(closes)
    if len(closes) < period + 1: return rsi_vals
    gains = sum(c for c in [closes[i]-closes[i-1] for i in range(1, period+1)] if c > 0)
    losses = sum(abs(c) for c in [closes[i]-closes[i-1] for i in range(1, period+1)] if c < 0)
    avg_gain, avg_loss = gains/period, losses/period
    rsi_vals[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain/avg_loss)))
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i-1]
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi_vals[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain/avg_loss)))
    return rsi_vals

def run_sim(candles, rsi_array, sl_pct, tp_pct):
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    
    position = None
    holding_times = []
    
    for i in range(30, len(candles)):
        rsi = rsi_array[i]
        if rsi is None: continue
        
        if position:
            if lows[i] <= position['sl']:
                holding_times.append(i - position['entry_idx'])
                position = None
            elif highs[i] >= position['tp']:
                holding_times.append(i - position['entry_idx'])
                position = None
            continue
            
        if rsi < 30:
            entry = closes[i]
            position = {
                'entry_idx': i,
                'sl': entry * (1 - sl_pct/100),
                'tp': entry * (1 + tp_pct/100),
            }
            
    if holding_times:
        avg_hold = sum(holding_times) / len(holding_times)
        print(f"  SL={sl_pct}% / TP={tp_pct}%:")
        print(f"    Total Trades: {len(holding_times)}")
        print(f"    Avg Holding (candles): {avg_hold:.1f}")
        print(f"    Avg Holding (hours): {avg_hold * 0.25:.1f}")

def main():
    print("Fetching data...")
    candles = fetch_wallex_15m(90)
    if not candles:
        print("No data fetched.")
        return
    closes = [c['c'] for c in candles]
    rsi = precompute_rsi(closes, 14)
    
    print("\n--- Holding Time Comparison ---")
    run_sim(candles, rsi, 1.5, 3.0)
    print("")
    run_sim(candles, rsi, 2.0, 4.0)

if __name__ == "__main__":
    main()
