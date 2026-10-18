#!/usr/bin/env python3
"""
backtest_m6_v3.py — Test Trend-Following and Breakout on Altcoins
- Mode 1: EMA Crossover (9/21) — Long only
- Mode 2: Donchian Breakout (20 period high) — Long only
- Split: FULL90 vs OOS45
- Fees included.
"""
import requests
import time

ASSETS = ["ETH", "SOL", "XRP"]
SL_PCT = 2.0
TP_PCT = 4.0
TOTAL_FEE = 0.6
POS_SIZE = 35000.0

def fetch_wallex_15m(symbol, days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    pair = f"{symbol}USDT"
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    candles.append({
                        "t": int(data['t'][i]), "h": float(data['h'][i]), 
                        "l": float(data['l'][i]), "c": float(data['c'][i]), 
                        "v": float(data['v'][i])
                    })
            elif not candles:
                pair = f"{symbol}TMN"
                url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={current}&to={to_ts}"
                r = requests.get(url, timeout=10)
                data = r.json()
                if data.get('s') == 'ok':
                    for i in range(len(data['t'])):
                        candles.append({
                            "t": int(data['t'][i]), "h": float(data['h'][i]), 
                            "l": float(data['l'][i]), "c": float(data['c'][i]), 
                            "v": float(data['v'][i])
                        })
        except Exception: pass
        current = to_ts
        time.sleep(0.3)
    candles.sort(key=lambda x: x['t'])
    return candles, pair

def ema(data, period):
    if len(data) < period: return [0]*len(data)
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    out = [0]*(period-1) + [e]
    for price in data[period:]:
        e = price * k + e * (1 - k)
        out.append(e)
    return out

def run_strategy(candles, start_idx, end_idx, mode):
    closes = [c['c'] for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    volumes = [c['v'] for c in candles]
    
    trades = []
    position = None
    equity = 1_000_000.0
    peak_eq = equity
    max_dd = 0.0
    
    for i in range(start_idx, end_idx):
        price = candles[i]['c']
        
        if position is not None:
            exit_p, pnl = None, None
            if candles[i]['l'] <= position['sl']:
                exit_p, pnl = position['sl'], -SL_PCT - TOTAL_FEE
            elif candles[i]['h'] >= position['tp']:
                exit_p, pnl = position['tp'], TP_PCT - TOTAL_FEE
                
            if exit_p is not None:
                equity += (pnl / 100) * POS_SIZE
                peak_eq = max(peak_eq, equity)
                max_dd = max(max_dd, (peak_eq - equity) / peak_eq * 100)
                position.update({"pnl": pnl})
                trades.append(position)
                position = None
            continue
            
        # Entry Logic
        if mode == "ema_cross":
            if ema9[i] == 0 or ema21[i] == 0: continue
            if ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1]:
                position = {'sl': price*(1-SL_PCT/100), 'tp': price*(1+TP_PCT/100)}
                
        elif mode == "breakout":
            if i < 21: continue
            # Volume filter: current vol > 1.5x average of last 20
            avg_vol = sum(volumes[i-20:i]) / 20.0
            if volumes[i] > (avg_vol * 1.5):
                high_20 = max(c['h'] for c in candles[i-20:i])
                if price > high_20:
                    position = {'sl': price*(1-SL_PCT/100), 'tp': price*(1+TP_PCT/100)}

    n = len(trades)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "dd": 0}
    wins = sum(1 for t in trades if t['pnl'] > 0)
    net = sum(t['pnl'] for t in trades)
    return {"n": n, "wr": wins/n*100, "net": net, "dd": max_dd}

def main():
    for symbol in ASSETS:
        candles, pair = fetch_wallex_15m(symbol, 90)
        if not candles or len(candles) < 50:
            print(f"{symbol}: Insufficient data.")
            continue
            
        mid = len(candles) // 2
        
        print(f"\n=== {symbol} ({pair}) ===")
        print(f"{'Strategy':<18} | {'OOS45 (n':>10} {'WR%':>6} {'Net%':>7} {'MaxDD%':>7}")
        print("-" * 55)
        
        res_ema = run_strategy(candles, mid, len(candles), "ema_cross")
        print(f"{'EMA Cross (9/21)':<18} | {res_ema['n']:>10} {res_ema['wr']:>6.1f} {res_ema['net']:>+7.1f} {res_ema['dd']:>7.1f}")
        
        res_brk = run_strategy(candles, mid, len(candles), "breakout")
        print(f"{'Breakout (20+Vol)':<18} | {res_brk['n']:>10} {res_brk['wr']:>6.1f} {res_brk['net']:>+7.1f} {res_brk['dd']:>7.1f}")

if __name__ == "__main__":
    main()
