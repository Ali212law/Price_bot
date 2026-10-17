#!/usr/bin/env python3
"""
backtest_3months.py — Fetch 3 months of 15m data, pre-calculate RSI, run DIP/TOP backtest
Optimized for speed (O(N) instead of O(N^2))
"""
import requests
import time
import json

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
                        "t": int(data['t'][i]), "c": float(data['c'][i])
                    })
            else:
                print(f"  Error chunk {current}: {data.get('s')}")
        except Exception as e:
            print(f"  Request error: {e}")
        current = to_ts
        time.sleep(0.5)
        
    print(f"Total 15m candles fetched: {len(candles)}")
    candles.sort(key=lambda x: x['t'])
    return candles

def precompute_rsi(closes, period=14):
    """محاسبه یک‌باره RSI برای کل آرایه (O(N))"""
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
    
    if avg_loss == 0: rsi_vals[period] = 100
    else:
        rs = avg_gain / avg_loss
        rsi_vals[period] = 100 - (100 / (1 + rs))
        
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i-1]
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0: rsi_vals[i] = 100
        else:
            rs = avg_gain / avg_loss
            rsi_vals[i] = 100 - (100 / (1 + rs))
            
    return rsi_vals

def main():
    candles = fetch_wallex_15m(90)
    print(f"Total candles ready: {len(candles)}")
    
    if not candles:
        print("No data to test.")
        return

    closes = [c['c'] for c in candles]
    ts = [c['t'] for c in candles]
    
    print("Pre-calculating RSI...")
    rsi_array = precompute_rsi(closes, period=14)
    
    trades = []
    position = None
    
    print("Running backtest...")
    for i in range(30, len(closes)):
        rsi = rsi_array[i]
        if rsi is None: continue
        
        # chg6h (24 candles of 15m)
        chg6h = ((closes[i] - closes[i-24]) / closes[i-24]) * 100 if i >= 24 else 0
        chg24h = ((closes[i] - closes[i-96]) / closes[i-96]) * 100 if i >= 96 else 0
        
        if position:
            entry = position['entry']
            current = closes[i]
            if position['side'] == 'buy':
                pnl_pct = (current - entry) / entry * 100
            else:
                pnl_pct = (entry - current) / entry * 100
                
            if pnl_pct <= -1.5:
                position['exit'] = current
                position['exit_ts'] = ts[i]
                position['reason'] = 'SL'
                position['net'] = pnl_pct - 0.6
                trades.append(position)
                position = None
            elif pnl_pct >= 3.0:
                position['exit'] = current
                position['exit_ts'] = ts[i]
                position['reason'] = 'TP'
                position['net'] = pnl_pct - 0.6
                trades.append(position)
                position = None
            continue
            
        # Entry logic
        side = None
        sig = None
        if rsi < 30: side, sig = 'buy', 'DIP'
        elif rsi > 75: side, sig = 'sell', 'TOP'
        
        if side:
            position = {
                'side': side, 'signal': sig, 'entry': closes[i],
                'entry_ts': ts[i], 'rsi': rsi, 'chg6h': chg6h, 'chg24h': chg24h
            }
            
    print(f"\nTotal trades simulated: {len(trades)}")
    if trades:
        wins = sum(1 for t in trades if t['net'] > 0)
        net_sum = sum(t['net'] for t in trades)
        print(f"Win Rate: {wins/len(trades)*100:.1f}%")
        print(f"Total Net % (sum): {net_sum:+.2f}%")
        
        print("\nBy Signal:")
        for sig in ['DIP', 'TOP']:
            grp = [t for t in trades if t['signal'] == sig]
            if not grp: continue
            w = sum(1 for t in grp if t['net'] > 0)
            n = sum(t['net'] for t in grp)
            print(f"  {sig}: n={len(grp)} | WR={w/len(grp)*100:.1f}% | sum_net={n:+.2f}%")
    else:
        print("No trades executed during this period.")

if __name__ == "__main__":
    main()
