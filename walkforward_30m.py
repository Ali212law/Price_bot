#!/usr/bin/env python3
# walkforward_30m.py — Test 30m timeframe for SOL and ETH (D-12)

import requests, json, time

ASSETS = ["SOLUSDT", "ETHUSDT"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
N_WINDOWS = 4
WARMUP = 50
TARGET_CANDLES = 2160 # ~45 days for 30m (But we want 4 windows of 750 = 3000. Let's fetch 3000)

def fetch_binance_vision(symbol, interval="30m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    while len(all_candles) < 3000:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&endTime={end_time}"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = r.json()
            if not data: break
            for k in data:
                all_candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])})
            end_time = data[0][0] - 1
        else: break
        time.sleep(0.5)
    
    seen, unique = set(), []
    for c in all_candles:
        if c["t"] not in seen:
            seen.add(c["t"]); unique.append(c)
    unique.sort(key=lambda x: x["t"])
    return unique[-3000:] # Get exactly last 3000

def compute_rsi(closes, period=14):
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

def backtest_window(candles, equity_start=1000000.0):
    closes = [c["c"] for c in candles]
    rsi_list = compute_rsi(closes)
    equity = equity_start
    trades = []
    open_pos = None
    i = WARMUP

    while i < len(candles):
        if open_pos is None:
            if rsi_list[i] is not None and rsi_list[i] < 30:
                entry = candles[i]["c"]
                # Fixed 2% SL, 4% TP
                open_pos = {"entry": entry, "sl": entry*0.98, "tp": entry*1.04, "idx": i}
        else:
            c = candles[i]
            exit_p = None
            if c["l"] <= open_pos["sl"]: exit_p = open_pos["sl"]
            elif c["h"] >= open_pos["tp"]: exit_p = open_pos["tp"]
            elif (i - open_pos["idx"]) >= 50: exit_p = c["c"]
            
            if exit_p:
                net_pct = ((exit_p - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2 # 0.2% fee
                equity += (equity * 0.005 * (net_pct / 2.0)) # Approximate risk 0.5%
                trades.append({"net_pct": net_pct})
                open_pos = None
        i += 1

    n = len(trades)
    wr = (sum(1 for t in trades if t["net_pct"] > 0) / n * 100) if n else 0
    net = sum(t["net_pct"] for t in trades)
    return n, round(wr, 1), round(net, 2)

def main():
    for symbol in ASSETS:
        print(f"\nFetching {symbol} 30m data...")
        candles = fetch_binance_vision(symbol)
        print(f"Total: {len(candles)} candles.")
        
        if len(candles) < 3000:
            print("Not enough data.")
            continue
            
        wsize = len(candles) // N_WINDOWS
        print(f"--- {symbol} (30m) ---")
        print(f"{'Win':<4} | {'n':>3} | {'WR%':>5} | {'Net%':>6}")
        
        pos_wins = 0
        for w in range(N_WINDOWS):
            s = w * wsize
            e = (w + 1) * wsize if w < N_WINDOWS - 1 else len(candles)
            n, wr, net = backtest_window(candles[s:e])
            if net > 0: pos_wins += 1
            print(f"W{w+1:<3} | {n:>3} | {wr:>5} | {net:>+6.2f}")
            
        print(f"Positive Windows: {pos_wins}/4")

if __name__ == "__main__":
    main()
