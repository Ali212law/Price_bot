#!/usr/bin/env python3
"""
backtest_global_v2.py — Optimizing Winning Strategies with ATR
- Tests winning combos from previous run.
- Compares Fixed SL (2%) vs ATR SL (1.5x, 2.0x).
"""
import json
import os

HISTORY_FILE = "global_history.json"
TP_PCT = 4.0
TOTAL_FEE = 0.1
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

def atr(data, period=14):
    atr_vals = [0.0] * len(data)
    if len(data) < period + 1: return atr_vals
    trs = []
    for i in range(1, len(data)):
        h, l, pc = data[i]['h'], data[i]['l'], data[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        if i >= period:
            atr_vals[i] = sum(trs[-period:]) / period
    return atr_vals

def run_strategy(candles, start_idx, end_idx, mode, sl_mode, atr_mult=1.5):
    closes = [c['c'] for c in candles]
    rsi_vals = rsi(closes)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    volumes = [c['v'] for c in candles]
    atr_vals = atr(candles)
    
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
                exit_p, pnl = position['sl'], -position['sl_pct'] - TOTAL_FEE
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
            
        # Logic
        trigger = False
        if mode == "dip" and rsi_vals[i] < 30:
            trigger = True
        elif mode == "breakout" and i > 20:
            high_20 = max(c['h'] for c in candles[i-20:i])
            avg_vol = sum(volumes[i-20:i]) / 20.0
            if price > high_20 and volumes[i] > avg_vol * 1.5:
                trigger = True

        if trigger:
            if sl_mode == "fixed":
                sl_p = 2.0
            else:
                # ATR based SL
                if atr_vals[i] == 0: continue
                sl_p = (atr_vals[i] * atr_mult / price) * 100
                sl_p = max(0.5, min(5.0, sl_p)) # Cap between 0.5% and 5%
                
            position = {
                'sl': price*(1-sl_p/100), 
                'tp': price*(1+TP_PCT/100),
                'sl_pct': sl_p
            }

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

    # Winning Combos from previous test: (Asset, Strategy)
    combos = [
        ("SOLUSDT", "dip"),
        ("SOLUSDT", "breakout"),
        ("ETHUSDT", "dip"),
        ("XRPUSDT", "breakout"),
        ("BTCUSDT", "breakout")
    ]

    for symbol, mode in combos:
        if symbol not in data:
            continue
        candles = data[symbol]
        total = len(candles)
        oos_start = int(total * 0.5)
        
        print(f"\n=== {symbol} | Strategy: {mode.upper()} ===")
        print(f"{'SL Mode':<15} | {'n':>4} {'WR%':>6} {'Net%':>7} {'MaxDD%':>7}")
        print("-" * 50)
        
        # Test Fixed SL
        res_fixed = run_strategy(candles, oos_start, total, mode, "fixed")
        print(f"{'Fixed (2.0%)':<15} | {res_fixed['n']:>4} {res_fixed['wr']:>6.1f} {res_fixed['net']:>+7.1f} {res_fixed['dd']:>7.1f}")
        
        # Test ATR SL (1.5x)
        res_atr15 = run_strategy(candles, oos_start, total, mode, "atr", atr_mult=1.5)
        print(f"{'ATR (1.5x)':<15} | {res_atr15['n']:>4} {res_atr15['wr']:>6.1f} {res_atr15['net']:>+7.1f} {res_atr15['dd']:>7.1f}")

        # Test ATR SL (2.0x)
        res_atr20 = run_strategy(candles, oos_start, total, mode, "atr", atr_mult=2.0)
        print(f"{'ATR (2.0x)':<15} | {res_atr20['n']:>4} {res_atr20['wr']:>6.1f} {res_atr20['net']:>+7.1f} {res_atr20['dd']:>7.1f}")

if __name__ == "__main__":
    main()
