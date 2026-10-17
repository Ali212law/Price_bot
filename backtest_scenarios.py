#!/usr/bin/env python3
"""
backtest_scenarios.py — 3 scenarios requested by AI2
Only DIP, triggers using High/Low, SL priority on conflict.
Equity curve starting at 1,000,000 Toman.
"""
import requests
import time
import json
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
                    # Keep OHLC, not just Close
                    candles.append({
                        "t": int(data['t'][i]), 
                        "o": float(data['o'][i]),
                        "h": float(data['h'][i]),
                        "l": float(data['l'][i]),
                        "c": float(data['c'][i])
                    })
        except Exception as e:
            print(f"  Request error: {e}")
        current = to_ts
        time.sleep(0.3)
    print(f"Total 15m candles: {len(candles)}")
    candles.sort(key=lambda x: x['t'])
    return candles

def precompute_rsi(closes, period=14):
    rsi_vals = [None] * len(closes)
    if len(closes) < period + 1: return rsi_vals
    gains = 0
    losses = 0
    for i in range(1, period + 1):
        change = closes[i] - closes[i-1]
        if change > 0: gains += change
        else: losses += abs(change)
    avg_gain = gains / period
    avg_loss = losses / period
    rsi_vals[period] = 100 if avg_loss == 0 else (100 - (100 / (1 + (avg_gain/avg_loss))))
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i-1]
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi_vals[i] = 100 if avg_loss == 0 else (100 - (100 / (1 + (avg_gain/avg_loss))))
    return rsi_vals

def classify_regime(chg24h):
    if chg24h is None: return "unknown"
    if chg24h > 1.5: return "bull"
    if chg24h < -1.5: return "bear"
    if abs(chg24h) < 0.5: return "range"
    return "chop"

def run_scenario(name, candles, rsi_array, sl_pct, tp_pct, filter_func=None):
    print(f"\n{'='*50}")
    print(f"SCENARIO: {name}")
    print(f"SL={sl_pct}% | TP={tp_pct}% | Filter={filter_func.__name__ if filter_func else 'None'}")
    print(f"{'='*50}")
    
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    
    trades = []
    position = None
    capital = 1_000_000.0
    equity_curve = [capital]
    
    for i in range(30, len(candles)):
        rsi = rsi_array[i]
        if rsi is None: continue
        
        chg24h = ((closes[i] - closes[i-96]) / closes[i-96]) * 100 if i >= 96 else 0
        
        if position:
            # Check SL and TP using High/Low
            # SL Priority
            if lows[i] <= position['sl']:
                exit_price = position['sl']
                reason = 'SL'
                net_pct = -sl_pct - 0.6
                position.update({'exit': exit_price, 'reason': reason, 'net': net_pct, 'exit_ts': candles[i]['t']})
                trades.append(position)
                capital *= (1 + net_pct/100)
                equity_curve.append(capital)
                position = None
            elif highs[i] >= position['tp']:
                exit_price = position['tp']
                reason = 'TP'
                net_pct = tp_pct - 0.6
                position.update({'exit': exit_price, 'reason': reason, 'net': net_pct, 'exit_ts': candles[i]['t']})
                trades.append(position)
                capital *= (1 + net_pct/100)
                equity_curve.append(capital)
                position = None
            continue
            
        # Entry (Only DIP, using close of current candle as entry)
        if rsi < 30:
            if filter_func and not filter_func(chg24h):
                continue
                
            entry = closes[i]
            position = {
                'side': 'buy',
                'entry': entry,
                'sl': entry * (1 - sl_pct/100),
                'tp': entry * (1 + tp_pct/100),
                'entry_ts': candles[i]['t'],
                'regime': classify_regime(chg24h)
            }
            
    # Summary
    n = len(trades)
    if n == 0:
        print("No trades executed.")
        return
        
    wins = sum(1 for t in trades if t['net'] > 0)
    sum_net = sum(t['net'] for t in trades)
    avg_net = sum_net / n
    
    print(f"Total trades: {n}")
    print(f"Win Rate:     {wins/n*100:.1f}%")
    print(f"Sum Net %:    {sum_net:+.2f}%")
    print(f"Avg Net %:    {avg_net:+.2f}%")
    print(f"Final Equity: {capital:,.0f} Toman")
    
    # Regime breakdown
    by_regime = defaultdict(list)
    for t in trades:
        by_regime[t['regime']].append(t)
        
    print("\nBy Regime:")
    for reg in sorted(by_regime.keys()):
        grp = by_regime[reg]
        w = sum(1 for t in grp if t['net'] > 0)
        sn = sum(t['net'] for t in grp)
        print(f"  {reg:6s}: n={len(grp):2d} | WR={w/len(grp)*100:5.1f}% | sum_net={sn:+7.2f}%")

def filter_C(chg24h):
    return -2.0 <= chg24h <= -1.5

def main():
    candles = fetch_wallex_15m(90)
    if not candles: return
    closes = [c['c'] for c in candles]
    
    print("Pre-calculating RSI...")
    rsi_array = precompute_rsi(closes, period=14)
    
    # Scenario A
    run_scenario("A: SL=2.0 / TP=4.0", candles, rsi_array, 2.0, 4.0)
    
    # Scenario B
    run_scenario("B: SL=1.0 / TP=2.0", candles, rsi_array, 1.0, 2.0)
    
    # Scenario C
    run_scenario("C: SL=1.5 / TP=3.0 + Filter", candles, rsi_array, 1.5, 3.0, filter_func=filter_C)
    
    print("\n" + "="*50)
    print("ALL SCENARIOS COMPLETE")
    print("="*50)

if __name__ == "__main__":
    main()
