#!/usr/bin/env python3
"""
backtest_scenario_d.py — Scenario D (DIP + EMA200 Filter)
"""
import requests
import time
from datetime import datetime, timezone
from collections import defaultdict

def fetch_wallex_15m(days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    print(f"Fetching {days} days of 15m data from Wallex...")
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
        except: pass
        current = to_ts
        time.sleep(0.3)
    candles.sort(key=lambda x: x['t'])
    print(f"Total candles: {len(candles)}")
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

def precompute_ema(closes, period=200):
    ema_vals = [None] * len(closes)
    if len(closes) < period: return ema_vals
    
    # SMA for the first period
    sma = sum(closes[:period]) / period
    ema_vals[period - 1] = sma
    k = 2.0 / (period + 1)
    
    for i in range(period, len(closes)):
        ema_vals[i] = closes[i] * k + ema_vals[i-1] * (1 - k)
    return ema_vals

def run_scenario(name, candles, rsi_array, ema_array):
    print(f"\n{'='*50}\nSCENARIO: {name}\n{'='*50}")
    
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    
    trades = []
    position = None
    capital = 1_000_000.0
    risk_per_trade = 700.0 # Fixed Toman risk
    sl_pct, tp_pct = 2.0, 4.0
    
    # Start loop after EMA warm-up
    start_idx = 200 
    
    for i in range(start_idx, len(candles)):
        rsi = rsi_array[i]
        ema = ema_array[i]
        if rsi is None or ema is None: continue
        
        chg24h = ((closes[i] - closes[i-96]) / closes[i-96]) * 100 if i >= 96 else 0
        
        if position:
            if lows[i] <= position['sl']:
                position['exit_price'] = position['sl']
                position['reason'] = 'SL'
                trades.append(position)
                capital -= position['risk_toman']
                position = None
            elif highs[i] >= position['tp']:
                position['exit_price'] = position['tp']
                position['reason'] = 'TP'
                trades.append(position)
                capital += position['risk_toman'] * (tp_pct / sl_pct)
                position = None
            continue
            
        # Entry Condition: DIP + Price > EMA 200
        if rsi < 30 and closes[i] > ema:
            entry = closes[i]
            position = {
                'entry': entry,
                'sl': entry * (1 - sl_pct/100),
                'tp': entry * (1 + tp_pct/100),
                'risk_toman': risk_per_trade,
                'regime': "bear" if chg24h < -1.5 else ("bull" if chg24h > 1.5 else ("range" if abs(chg24h) < 0.5 else "chop"))
            }
            
    n = len(trades)
    if n == 0:
        print("No trades executed.")
        return
        
    wins = sum(1 for t in trades if t['reason'] == 'TP')
    print(f"Total trades: {n}")
    print(f"Win Rate:     {wins/n*100:.1f}%")
    print(f"Final Equity: {capital:,.0f} Toman")
    
    by_regime = defaultdict(list)
    for t in trades: by_regime[t['regime']].append(t)
    print("\nBy Regime:")
    for reg in sorted(by_regime.keys()):
        grp = by_regime[reg]
        w = sum(1 for t in grp if t['reason'] == 'TP')
        print(f"  {reg:6s}: n={len(grp):2d} | WR={w/len(grp)*100:5.1f}%")

def main():
    candles = fetch_wallex_15m(90)
    if not candles: return
    
    closes = [c['c'] for c in candles]
    print("Pre-calculating RSI (14)...")
    rsi_array = precompute_rsi(closes, 14)
    
    print("Pre-calculating EMA (200)...")
    ema_array = precompute_ema(closes, 200)
    
    run_scenario("D: DIP + Price > EMA 200", candles, rsi_array, ema_array)

if __name__ == "__main__":
    main()
