#!/usr/bin/env python3
"""
backtest_scenario_e.py — Scenario E (Trailing Stop / Dynamic Exit)
"""
import requests
import time
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

def run_scenario_e(candles, rsi_array):
    print(f"\n{'='*50}\nSCENARIO: E (Trailing Stop)\n{'='*50}")
    
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    
    trades = []
    position = None
    capital = 1_000_000.0
    risk_toman = 700.0
    sl_pct = 2.0
    pos_size = risk_toman / (sl_pct / 100) # 35,000 Toman
    
    for i in range(30, len(candles)):
        rsi = rsi_array[i]
        if rsi is None: continue
        
        chg24h = ((closes[i] - closes[i-96]) / closes[i-96]) * 100 if i >= 96 else 0
        
        if position is None:
            # Entry Logic (M2 Baseline)
            if rsi < 30:
                position = {
                    'entry': closes[i],
                    'sl': closes[i] * (1 - sl_pct/100),
                    'max_price': closes[i],
                    'trailing_active': False,
                    'regime': "bear" if chg24h < -1.5 else ("bull" if chg24h > 1.5 else ("range" if abs(chg24h) < 0.5 else "chop"))
                }
        else:
            # Exit Management
            # 1. Check Hard Stop-Loss first (Conservative)
            if lows[i] <= position['sl']:
                exit_price = position['sl']
                reason = 'Hard_SL'
            else:
                # 2. Update max price reached
                position['max_price'] = max(position['max_price'], highs[i])
                
                # 3. Check Activation (+2% profit)
                if not position['trailing_active'] and highs[i] >= position['entry'] * 1.02:
                    position['trailing_active'] = True
                    
                # 4. Check Trailing Stop if active
                if position['trailing_active']:
                    trail_sl = position['max_price'] * 0.98
                    if lows[i] <= trail_sl:
                        exit_price = trail_sl
                        reason = 'Trail_SL'
                    else:
                        continue # Still open, trail not hit
                else:
                    continue # Still open, not yet activated
            
            # If we reach here, we exited
            pnl_pct = (exit_price - position['entry']) / position['entry'] * 100
            net_pct = pnl_pct - 0.6 # Deduct 0.6% cost
            capital += (net_pct / 100) * pos_size
            
            position['exit'] = exit_price
            position['reason'] = reason
            position['net_pct'] = net_pct
            trades.append(position)
            position = None
            
    # Summary
    n = len(trades)
    if n == 0:
        print("No trades executed.")
        return
        
    wins = [t['net_pct'] for t in trades if t['net_pct'] > 0]
    losses = [t['net_pct'] for t in trades if t['net_pct'] <= 0]
    win_rate = len(wins) / n * 100
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses else float('inf')
    
    print(f"Total trades: {n}")
    print(f"Win Rate:     {win_rate:.1f}%")
    print(f"Avg Win:      {avg_win:+.2f}%")
    print(f"Avg Loss:     {avg_loss:+.2f}%")
    print(f"Profit Factor:{profit_factor:.2f}")
    print(f"Final Equity: {capital:,.0f} Toman")
    
    by_regime = defaultdict(list)
    for t in trades: by_regime[t['regime']].append(t)
    print("\nBy Regime:")
    for reg in sorted(by_regime.keys()):
        grp = by_regime[reg]
        w = sum(1 for t in grp if t['net_pct'] > 0)
        print(f"  {reg:6s}: n={len(grp):2d} | WR={w/len(grp)*100:5.1f}%")

def main():
    candles = fetch_wallex_15m(90)
    if not candles: return
    
    closes = [c['c'] for c in candles]
    print("Pre-calculating RSI (14)...")
    rsi_array = precompute_rsi(closes, 14)
    
    run_scenario_e(candles, rsi_array)

if __name__ == "__main__":
    main()
