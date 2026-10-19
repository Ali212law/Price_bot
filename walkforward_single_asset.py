#!/usr/bin/env python3
# walkforward_single_asset.py - Isolated Walk-Forward per asset

import requests, json, time, os

HEADERS = {"User-Agent": "Mozilla/5.0"}
N_WINDOWS = 4
WARMUP = 50
TARGET_CANDLES = 3000

# لیست ۱۰ ارز برتری که در تست قبلی پیدا شد
ASSETS = ["BTCUSDT", "ETHUSDT", "ZECUSDT", "SOLUSDT", "NEARUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "SUIUSDT"]

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

def ema(data, period):
    if len(data) < period: return [0]*len(data)
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    out = [0]*(period-1) + [e]
    for price in data[period:]:
        e = price * k + e * (1 - k)
        out.append(e)
    return out

def backtest_isolation(candles):
    closes = [c["c"] for c in candles]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    
    trades = []
    open_pos = None
    
    for i in range(WARMUP, len(candles)):
        c = candles[i]
        
        if open_pos is not None:
            # Trailing stop update
            new_sl = c["c"] * 0.98
            if new_sl > open_pos["sl"]:
                open_pos["sl"] = new_sl
                
            exit_price = None
            if c["l"] <= open_pos["sl"]:
                exit_price = open_pos["sl"]
            elif (i - open_pos["entry_idx"]) >= 100: 
                exit_price = c["c"]
            
            if exit_price:
                net_pct = ((exit_price - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
                trades.append({"net_pct": net_pct})
                open_pos = None
        else:
            if ema9[i] > 0 and ema21[i] > 0:
                # Bullish Cross
                if ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1]:
                    open_pos = {"entry_idx": i, "entry": c["c"], "sl": c["c"] * 0.98}

    if open_pos is not None:
        net_pct = ((candles[-1]["c"] - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
        trades.append({"net_pct": net_pct})

    n = len(trades)
    wr = (sum(1 for t in trades if t["net_pct"] > 0) / n * 100) if n else 0
    net = sum(t["net_pct"] for t in trades)
    return {"n": n, "wr": round(wr, 1), "net": round(net, 2)}

def main():
    results = {}
    for sym in ASSETS:
        print(f"\nFetching {sym}...")
        candles = fetch_binance_vision(sym)
        if len(candles) < TARGET_CANDLES: continue
            
        wsize = len(candles) // N_WINDOWS
        print(f"--- {sym} (Isolated) ---")
        sym_res = []
        pos_wins = 0
        
        for w in range(N_WINDOWS):
            s = w * wsize
            e = (w + 1) * wsize if w < N_WINDOWS - 1 else len(candles)
            res = backtest_isolation(candles[s:e])
            sym_res.append(res)
            if res['net'] > 0: pos_wins += 1
            print(f"W{w+1}: n={res['n']}, WR={res['wr']}%, Net={res['net']}%")
            
        results[sym] = {"windows": sym_res, "pos_wins": pos_wins}
        print(f"-> {sym} Positive Windows: {pos_wins}/4")

    with open("walkforward_single_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: walkforward_single_results.json")

if __name__ == "__main__":
    main()
