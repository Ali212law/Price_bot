#!/usr/bin/env python3
# walkforward_m2.py — Walk-Forward 4-window for Paper 35 (M2 Logic)
# Strategy: DIP (RSI<30), Fixed SL=2%, TP=4%, 15m timeframe
# Data: Wallex BTCTMN (Fallback to local btc_history.json)

import json, os, requests, time

N_WINDOWS = 4
WARMUP = 50
RSI_PERIOD = 14
SL_PCT = 2.0
TP_PCT = 4.0
TOTAL_FEE = 0.6

def fetch_wallex_15m(days=90):
    print(f"Fetching {days} days of Wallex 15m data...")
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    current = start
    
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol=BTCTMN&resolution=15&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    c = float(data['c'][i])
                    if c > 100_000_000_000: c /= 10
                    candles.append({
                        "t": int(data['t'][i]),
                        "h": float(data['h'][i])/(10 if float(data['h'][i])>100_000_000_000 else 1),
                        "l": float(data['l'][i])/(10 if float(data['l'][i])>100_000_000_000 else 1),
                        "c": c
                    })
        except Exception as e:
            print(f"Fetch error: {e}")
        current = to_ts
        time.sleep(0.3)
        
    candles.sort(key=lambda x: x['t'])
    return candles

def calc_rsi(closes, period=14):
    n = len(closes)
    rsi = [None] * n
    if n <= period: return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        chg = closes[i] - closes[i-1]
        gains.append(max(chg, 0)); losses.append(max(-chg, 0))
    avg_g = sum(gains) / period; avg_l = sum(losses) / period
    rsi[period] = 100.0 if avg_l == 0 else 100 - (100 / (1 + (avg_g / avg_l)))
    for i in range(period + 1, n):
        chg = closes[i] - closes[i-1]
        avg_g = (avg_g * (period - 1) + max(chg, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-chg, 0)) / period
        rsi[i] = 100.0 if avg_l == 0 else 100 - (100 / (1 + (avg_g / avg_l)))
    return rsi

def backtest_window(candles):
    closes = [c['c'] for c in candles]
    rsi = calc_rsi(closes)
    trades = []
    open_pos = None
    
    for i in range(WARMUP, len(candles)):
        if open_pos:
            c = candles[i]
            if c['l'] <= open_pos['sl']:
                pnl = -SL_PCT - TOTAL_FEE
                trades.append({"pnl": pnl}); open_pos = None
            elif c['h'] >= open_pos['tp']:
                pnl = TP_PCT - TOTAL_FEE
                trades.append({"pnl": pnl}); open_pos = None
        else:
            if rsi[i] is not None and rsi[i] < 30:
                entry = candles[i]['c']
                open_pos = {"entry": entry, "sl": entry*(1-SL_PCT/100), "tp": entry*(1+TP_PCT/100)}
                
    if open_pos:
        # Close dangling
        pnl = ((candles[-1]['c'] - open_pos['entry']) / open_pos['entry'] * 100) - TOTAL_FEE
        trades.append({"pnl": pnl})

    n = len(trades)
    wins = sum(1 for t in trades if t['pnl'] > 0)
    wr = (wins / n * 100) if n else 0
    net = sum(t['pnl'] for t in trades)
    return {"n": n, "wr": round(wr, 1), "net": round(net, 2)}

def main():
    if not os.path.exists("btc_history.json"):
        print("btc_history.json not found. Please run fetch first.")
        return
        
    with open("btc_history.json") as f:
        raw_data = json.load(f)
        
    # btc_history.json saves [time_str, price] pairs
    # We need to resample to 15m candles for accurate SL/TP hit logic
    print(f"Loaded {len(raw_data)} price records.")
    
    # For accurate high/low, we MUST fetch from Wallex if possible (since btc_history only has close prices)
    # Let's try fetching fresh 15m candles
    candles = fetch_wallex_15m(90)
    if len(candles) < 1000:
        print("Failed to fetch enough Wallex data. Aborting.")
        return
        
    total_len = len(candles)
    wsize = total_len // N_WINDOWS
    
    print(f"\n=== Paper 35 (M2) Walk-Forward on Wallex 15m ===")
    print(f"{'Window':<8} | {'n':>4} {'WR%':>6} {'Net%':>7}")
    print("-" * 40)
    
    pos_wins = 0
    for w in range(N_WINDOWS):
        s = w * wsize
        e = (w + 1) * wsize if w < N_WINDOWS - 1 else total_len
        res = backtest_window(candles[s:e])
        if res['net'] > 0: pos_wins += 1
        print(f"W{w+1:<7} | {res['n']:>4} {res['wr']:>6.1f} {res['net']:>+7.2f}")

    print(f"\nPositive Windows: {pos_wins}/4")
    if pos_wins >= 3:
        print(">> VERDICT: PASSED (Paper 35 shows real edge)")
    else:
        print(">> VERDICT: FAILED (Paper 35 is likely a zombie strategy)")

if __name__ == "__main__":
    main()
