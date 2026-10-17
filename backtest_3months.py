#!/usr/bin/env python3
"""
backtest_3months.py — Fetch 3 months of 15m data directly from Wallex
"""
import requests
import time
import json

def fetch_wallex_15m(days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600  # 14 days per request for 15m data
    candles = []
    
    print(f"Fetching {days} days of 15m data from Wallex...")
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        # We request 15m resolution directly
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
                print(f"  Chunk OK: {n} candles")
            else:
                print(f"  Error chunk {current}: {data.get('s')}")
        except Exception as e:
            print(f"  Request error: {e}")
        current = to_ts
        time.sleep(0.5)
        
    print(f"Total 15m candles fetched: {len(candles)}")
    # Sort just in case
    candles.sort(key=lambda x: x['t'])
    return candles

def calc_rsi(prices, period=14):
    if len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        ch = prices[i] - prices[i-1]
        if ch > 0: gains.append(ch); losses.append(0)
        else: gains.append(0); losses.append(abs(ch))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0: return 100
    rs = ag / al
    return round(100 - (100 / (1 + rs)), 2)

def main():
    candles_15m = fetch_wallex_15m(90)
    print(f"Total candles ready: {len(candles_15m)}")
    
    if not candles_15m:
        print("No data to test.")
        return

    closes = [c['c'] for c in candles_15m]
    ts = [c['t'] for c in candles_15m]
    
    trades = []
    position = None
    
    print("Running backtest...")
    for i in range(30, len(candles_15m)):
        rsi = calc_rsi(closes[:i+1])
        if rsi is None: continue
        
        # chg6h (24 candles of 15m = 6 hours)
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
            
        # Entry logic (simplified: just RSI + Priority)
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

if __name__ == "__main__":
    main()
