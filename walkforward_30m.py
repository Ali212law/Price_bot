#!/usr/bin/env python3
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
            else:
                print(f"  [HTTP Error] {r.status_code}: {r.text[:100]}")
                break
        except Exception as e:
            print(f"  [Fetch Error] {e}")
            break
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

def backtest_window(candles):
    closes = [c["c"] for c in candles]
    rsi_list = compute_rsi(closes)
    trades = []
    open_pos = None
    i = WARMUP

    while i < len(candles):
        if open_pos is None:
            if rsi_list[i] is not None and rsi_list[i] < 30:
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
        print(f"Fetching {symbol} 30m data...")
        candles = fetch_binance_vision(symbol)
        if len(candles) < TARGET_CANDLES:
            print(f"Not enough data for {symbol}: {len(candles)} candles.")
            results[symbol] = {"error": f"Not enough data: {len(candles)}"}
            continue
            
        wsize = len(candles) // N_WINDOWS
        sym_res = []
        print(f"--- {symbol} (30m) ---")
        for w in range(N_WINDOWS):
            s = w * wsize
            e = (w + 1) * wsize if w < N_WINDOWS - 1 else len(candles)
            res = backtest_window(candles[s:e])
            res["window"] = w + 1
            sym_res.append(res)
            print(f"W{w+1}: n={res['n']} WR={res['wr']}% Net={res['net']}%")
        
        pos_wins = sum(1 for r in sym_res if r['net'] > 0)
        results[symbol] = {"windows": sym_res, "pos_wins": pos_wins}
        print(f"{symbol} Positive Windows: {pos_wins}/4")

    with open("walkforward_30m_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved: walkforward_30m_results.json")

if __name__ == "__main__":
    main()
