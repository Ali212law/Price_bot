#!/usr/bin/env python3
"""
backtest_global.py — Test strategies on Global Market Data (Binance 1H)
- Tests: Pure DIP, EMA Cross, Breakout.
- Split: FULL (all data) and OOS (last 45 days).
"""
import json
import os

HISTORY_FILE = "global_history.json"
SL_PCT = 2.0
TP_PCT = 4.0
TOTAL_FEE = 0.1 # Binance fee is ~0.1% per side
POS_SIZE = 35000.0

def ema(data, period):
    if len(data) < period: return [0]*len(data)
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    out = [0]*(period-1) + [e]
    for price in data[period:]:
        e = price * k + e * (1 - k)
        out.append(e)
    return out

def rsi(data, period=14):
    if len(data) < period + 1: return [50.0]*len(data)
    rsi_vals = [50.0] * len(data)
    gains, losses = 0, 0
    for i in range(1, period + 1):
        ch = data[i] - data[i-1]
        if ch > 0: gains += ch
        else: losses += abs(ch)
    ag, al = gains/period, losses/period
    rsi_vals[period] = 100 - (100/(1+ag/al)) if al > 0 else 100
    for i in range(period + 1, len(data)):
        ch = data[i] - data[i-1]
        gain = ch if ch > 0 else 0
        loss = abs(ch) if ch < 0 else 0
        ag = (ag * (period - 1) + gain) / period
        al = (al * (period - 1) + loss) / period
        rsi_vals[i] = 100 - (100/(1+ag/al)) if al > 0 else 100
    return rsi_vals

def run_strategy(candles, start_idx, end_idx, mode):
    closes = [c['c'] for c in candles]
    rsi_vals = rsi(closes)
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
            
        if mode == "dip" and rsi_vals[i] < 30:
            position = {'sl': price*(1-SL_PCT/100), 'tp': price*(1+TP_PCT/100)}
        elif mode == "ema" and ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1]:
            position = {'sl': price*(1-SL_PCT/100), 'tp': price*(1+TP_PCT/100)}
        elif mode == "breakout" and i > 20:
            high_20 = max(c['h'] for c in candles[i-20:i])
            avg_vol = sum(volumes[i-20:i]) / 20.0
            if price > high_20 and volumes[i] > avg_vol * 1.5:
                position = {'sl': price*(1-SL_PCT/100), 'tp': price*(1+TP_PCT/100)}

    n = len(trades)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "dd": 0}
    wins = sum(1 for t in trades if t['pnl'] > 0)
    net = sum(t['pnl'] for t in trades)
    return {"n": n, "wr": wins/n*100, "net": net, "dd": max_dd}

def main():
    if not os.path.exists(HISTORY_FILE):
        print(f"File {HISTORY_FILE} not found.")
        return
        
    with open(HISTORY_FILE) as f:
        data = json.load(f)

    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
        if symbol not in data:
            print(f"{symbol}: No data.")
            continue
            
        candles = data[symbol]
        total = len(candles)
        oos_start = int(total * 0.5) # Start OOS from halfway point
        
        print(f"\n=== {symbol} | Total: {total} | OOS Start: {oos_start} ===")
        print(f"{'Strategy':<15} | {'n':>4} {'WR%':>6} {'Net%':>7} {'MaxDD%':>7}")
        print("-" * 50)
        
        for mode in ["dip", "ema", "breakout"]:
            res = run_strategy(candles, oos_start, total, mode)
            print(f"{mode.upper():<15} | {res['n']:>4} {res['wr']:>6.1f} {res['net']:>+7.1f} {res['dd']:>7.1f}")

if __name__ == "__main__":
    main()
