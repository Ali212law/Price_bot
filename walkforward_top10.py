#!/usr/bin/env python3
# walkforward_top10.py — D-14: Test Top 10 Volume Assets on 1H

import requests, json, time, os

HEADERS = {"User-Agent": "Mozilla/5.0"}
N_WINDOWS = 4
WARMUP = 50
TARGET_CANDLES = 3000
STABLECOINS = ["USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "BUSD", "AEUR"]

def get_top_10_assets():
    print("Fetching top 10 assets by volume...")
    url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    r = requests.get(url, headers=HEADERS, timeout=20)
    data = r.json()
    
    usdt_pairs = []
    for item in data:
        symbol = item["symbol"]
        if symbol.endswith("USDT"):
            base = symbol.replace("USDT", "")
            if base not in STABLECOINS:
                vol = float(item["quoteVolume"])
                usdt_pairs.append({"symbol": symbol, "volume": vol})
                
    usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
    top_10 = [x["symbol"] for x in usdt_pairs[:10]]
    print(f"Top 10: {top_10}")
    return top_10

def fetch_binance_vision(symbol, interval="1h", limit=1000):
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
        time.sleep(0.3)
    
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

def is_breakout(candles, idx, lookback=20):
    if idx < lookback: return False
    return candles[idx]["c"] > max(c["h"] for c in candles[idx-lookback:idx])

def backtest_window(candles_dict, start_idx, end_idx):
    trades = []
    open_pos = None
    
    # Precompute indicators
    indicators = {}
    for sym, candles in candles_dict.items():
        closes = [c["c"] for c in candles]
        indicators[sym] = {"rsi": compute_rsi(closes)}

    for i in range(start_idx, end_idx):
        # 1. Check Exit
        if open_pos is not None:
            c = candles_dict[open_pos["symbol"]][i]
            hit_sl = c["l"] <= open_pos["sl"]
            hit_tp = c["h"] >= open_pos["tp"]
            exit_price = None
            
            if hit_sl: exit_price = open_pos["sl"]
            elif hit_tp: exit_price = open_pos["tp"]
            elif (i - open_pos["entry_idx"]) >= 50: exit_price = c["c"]
            
            if exit_price:
                net_pct = ((exit_price - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2 # 0.2% fee
                trades.append({"net_pct": net_pct})
                open_pos = None
                
        # 2. Check Entry (Only 1 trade at a time across all assets)
        if open_pos is None:
            for sym, candles in candles_dict.items():
                if i >= len(candles): continue
                
                signal = False
                # We test both DIP and Breakout for all assets
                if indicators[sym]["rsi"][i] is not None and indicators[sym]["rsi"][i] < 30: 
                    signal = True
                elif is_breakout(candles, i, 20):
                    signal = True
                    
                if signal:
                    entry = candles[i]["c"]
                    open_pos = {"symbol": sym, "entry_idx": i, "entry": entry, "sl": entry*0.98, "tp": entry*1.04}
                    break # Only 1 position

    if open_pos is not None:
        c = candles_dict[open_pos["symbol"]][-1]
        net_pct = ((c["c"] - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
        trades.append({"net_pct": net_pct})

    n = len(trades)
    wr = (sum(1 for t in trades if t["net_pct"] > 0) / n * 100) if n else 0
    net = sum(t["net_pct"] for t in trades)
    return {"n": n, "wr": round(wr, 1), "net": round(net, 2)}

def main():
    top_10 = get_top_10_assets()
    candles_dict = {}
    
    print("\nFetching data for top 10 assets...")
    for sym in top_10:
        print(f"Fetching {sym}...")
        candles = fetch_binance_vision(sym)
        if len(candles) < TARGET_CANDLES:
            print(f"Skipping {sym} (not enough data).")
            continue
        candles_dict[sym] = candles
        
    if len(candles_dict) < 5:
        print("Not enough assets fetched. Aborting.")
        return
        
    total_len = min(len(c) for c in candles_dict.values())
    wsize = total_len // N_WINDOWS
    
    results = []
    print("\n=== Walk-Forward (Top 10, 1H, 1-Position Limit) ===")
    print(f"{'Win':<4} | {'n':>3} | {'WR%':>5} | {'Net%':>6}")
    print("-" * 30)
    
    for w in range(N_WINDOWS):
        s = w * wsize
        e = (w + 1) * wsize if w < N_WINDOWS - 1 else total_len
        
        # Slice candles for this window
        window_dict = {sym: c[s:e] for sym, c in candles_dict.items()}
        res = backtest_window(window_dict, 0, len(window_dict[top_10[0]])) # WARMUP is inside
        
        # Note: WARMUP needs to be applied inside backtest_window or handled by slicing s+WARMUP
        # For simplicity, we just start from index 50
        res = backtest_window(window_dict, 50, len(window_dict[top_10[0]]))
        
        results.append(res)
        print(f"W{w+1:<3} | {res['n']:>3} | {res['wr']:>5} | {res['net']:>+6.2f}")
        
    with open("walkforward_top10_results.json", "w", encoding="utf-8") as f:
        json.dump({"assets": list(candles_dict.keys()), "results": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: walkforward_top10_results.json")

if __name__ == "__main__":
    main()
