#!/usr/bin/env python3
# walkforward_grid.py - D-13 Grid Test (30m)

import requests, json, time, os

ASSETS = ["SOLUSDT", "ETHUSDT"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
N_WINDOWS = 4
WARMUP = 50
TARGET_CANDLES = 3000

def fetch_binance_vision(symbol, interval="30m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    while len(all_candles) < TARGET_CANDLES:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&endTime={end_time}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])})
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.5)
    seen, unique = set(), []
    for c in all_candles:
        if c["t"] not in seen:
            seen.add(c["t"]); unique.append(c)
    unique.sort(key=lambda x: x["t"])
    return unique[-TARGET_CANDLES:]

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

def is_breakout(candles, idx, lookback):
    if idx < lookback: return False
    return candles[idx]["c"] > max(c["h"] for c in candles[idx-lookback:idx])

def backtest(candles, mode, param):
    closes = [c["c"] for c in candles]
    rsi_list = compute_rsi(closes)
    trades = []
    open_pos = None
    i = WARMUP

    while i < len(candles):
        if open_pos is None:
            signal = False
            if mode == "DIP" and rsi_list[i] is not None and rsi_list[i] < param: signal = True
            elif mode == "BREAKOUT" and is_breakout(candles, i, param): signal = True
            
            if signal:
                entry = candles[i]["c"]
                open_pos = {"entry": entry, "sl": entry*0.98, "tp": entry*1.04, "idx": i}
        else:
            c = candles[i]
            exit_p = None
            if c["l"] <= open_pos["sl"]: exit_p = open_pos["sl"]
            elif c["h"] >= open_pos["tp"]: exit_p = open_pos["tp"]
            elif (i - open_pos["idx"]) >= 50: exit_p = c["c"]
            
            if exit_p:
                net_pct = ((exit_p - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
                trades.append({"net_pct": net_pct})
                open_pos = None
        i += 1

    n = len(trades)
    wr = (sum(1 for t in trades if t["net_pct"] > 0) / n * 100) if n else 0
    net = sum(t["net_pct"] for t in trades)
    return {"n": n, "wr": round(wr, 1), "net": round(net, 2)}

def main():
    results = {}
    for symbol in ASSETS:
        print(f"\nFetching {symbol} 30m data...")
        candles = fetch_binance_vision(symbol)
        if len(candles) < TARGET_CANDLES:
            print("Not enough data."); continue
            
        wsize = len(candles) // N_WINDOWS
        w1 = candles[0:wsize]
        w2 = candles[wsize:2*wsize]
        w3 = candles[2*wsize:3*wsize]
        w4 = candles[3*wsize:]

        # 4 Combination Grid
        configs = [
            ("DIP", 30), ("DIP", 35), 
            ("BREAKOUT", 20), ("BREAKOUT", 10)
        ]
        
        best_config = None
        best_is_net = -9999
        
        print(f"--- {symbol} Optimization (W1+W2) ---")
        for mode, param in configs:
            r1 = backtest(w1, mode, param)
            r2 = backtest(w2, mode, param)
            total_is_net = r1["net"] + r2["net"]
            total_is_n = r1["n"] + r2["n"]
            
            print(f"{mode} ({param}): W1 Net={r1['net']}% (n={r1['n']}), W2 Net={r2['net']}% (n={r2['n']}) | Total IS Net={total_is_net}% (n={total_is_n})")
            
            if total_is_net > best_is_net:
                best_is_net = total_is_net
                best_config = (mode, param, total_is_n)
                
        # Validation on W3+W4 with best config
        mode, param, is_n = best_config
        print(f"\n--- {symbol} Validation (W3+W4) with BEST config: {mode} ({param}) ---")
        r3 = backtest(w3, mode, param)
        r4 = backtest(w4, mode, param)
        
        print(f"W3: n={r3['n']}, WR={r3['wr']}%, Net={r3['net']}%")
        print(f"W4: n={r4['n']}, WR={r4['wr']}%, Net={r4['net']}%")
        
        results[symbol] = {
            "best_config": f"{mode}_{param}",
            "IS_Net": best_is_net,
            "W3_Net": r3["net"], "W3_n": r3["n"],
            "W4_Net": r4["net"], "W4_n": r4["n"]
        }

    with open("walkforward_grid_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: walkforward_grid_results.json")

if __name__ == "__main__":
    main()
