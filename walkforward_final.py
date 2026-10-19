#!/usr/bin/env python3
# walkforward_final.py — E1 (4H DIP+Regime), E2 (1H BB+RSI), E3 (Buy&Hold)

import json, requests, time

HEADERS = {"User-Agent": "Mozilla/5.0"}
N_WINDOWS = 4
WARMUP = 50

def calc_ema(closes, period):
    if len(closes) < period: return [0]*len(closes)
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    out = [0]*(period-1) + [e]
    for price in closes[period:]:
        e = price * k + e * (1 - k)
        out.append(e)
    return out

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

def calc_atr(candles, period=14):
    n = len(candles)
    atr = [0.0] * n
    if n <= period: return atr
    trs = []
    for i in range(1, n):
        tr = max(candles[i]["h"] - candles[i]["l"], abs(candles[i]["h"] - candles[i-1]["c"]), abs(candles[i]["l"] - candles[i-1]["c"]))
        trs.append(tr)
        if i >= period:
            atr[i] = sum(trs[-period:]) / period
    return atr

def calc_bb(closes, period=20, std_dev=2):
    n = len(closes)
    lower = [0.0] * n
    if n < period: return lower
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = variance ** 0.5
        lower[i] = sma - (std_dev * std)
    return lower

def fetch_1h_data(symbol):
    all_candles = []
    end_time = int(time.time() * 1000)
    while len(all_candles) < 3000:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit=1000&endTime={end_time}"
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
    unique = sorted({c["t"]: c for c in all_candles}.values(), key=lambda x: x["t"])
    return unique[-3000:]

def run_e1_dip_4h(candles, btc_regime):
    closes = [c["c"] for c in candles]
    rsi = calc_rsi(closes)
    atr = calc_atr(candles)
    trades, open_pos = [], None
    
    for i in range(WARMUP, len(candles)):
        if open_pos:
            c = candles[i]
            if c["l"] <= open_pos["sl"]: exit_p = open_pos["sl"]
            elif c["h"] >= open_pos["tp"]: exit_p = open_pos["tp"]
            elif (i - open_pos["idx"]) >= 50: exit_p = c["c"]
            else: continue
            net = ((exit_p - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
            trades.append(net); open_pos = None
        elif rsi[i] and rsi[i] < 30 and btc_regime[i]:
            if atr[i] > 0:
                sl_dist = 2 * atr[i]
                open_pos = {"entry": candles[i]["c"], "sl": candles[i]["c"] - sl_dist, "tp": candles[i]["c"] + (2 * sl_dist), "idx": i}
    if open_pos:
        trades.append(((candles[-1]["c"] - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2)
    return sum(trades), len(trades)

def run_e2_bb_1h(candles):
    closes = [c["c"] for c in candles]
    rsi = calc_rsi(closes)
    atr = calc_atr(candles)
    lower_bb = calc_bb(closes)
    trades, open_pos = [], None
    
    for i in range(WARMUP, len(candles)):
        if open_pos:
            c = candles[i]
            if c["l"] <= open_pos["sl"]: exit_p = open_pos["sl"]
            elif c["h"] >= open_pos["tp"]: exit_p = open_pos["tp"]
            elif (i - open_pos["idx"]) >= 50: exit_p = c["c"]
            else: continue
            net = ((exit_p - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2
            trades.append(net); open_pos = None
        elif lower_bb[i] > 0 and candles[i]["c"] <= lower_bb[i] and rsi[i] and rsi[i] < 35:
            if atr[i] > 0:
                sl_dist = 2 * atr[i]
                open_pos = {"entry": candles[i]["c"], "sl": candles[i]["c"] - sl_dist, "tp": candles[i]["c"] + (2 * sl_dist), "idx": i}
    if open_pos:
        trades.append(((candles[-1]["c"] - open_pos["entry"]) / open_pos["entry"] * 100) - 0.2)
    return sum(trades), len(trades)

def main():
    with open("deep_history_4h.json") as f:
        data_4h = json.load(f)
    
    if "BTCUSDT" not in data_4h: return
    btc_closes = [c["c"] for c in data_4h["BTCUSDT"]]
    btc_ema200 = calc_ema(btc_closes, 200)
    
    results = {}
    print("=== Starting E1, E2, E3 ===")
    
    for sym, candles_4h in data_4h.items():
        print(f"\nProcessing {sym}...")
        total_4h = len(candles_4h)
        wsize_4h = total_4h // N_WINDOWS
        
        # Fetch 1H data for E2
        print(f"  Fetching 1H data for E2...")
        candles_1h = fetch_1h_data(sym)
        total_1h = len(candles_1h)
        wsize_1h = total_1h // N_WINDOWS
        
        sym_res = {"E1": [], "E2": [], "E3": []}
        
        for w in range(N_WINDOWS):
            # E1 (4H)
            s4 = w * wsize_4h; e4 = (w + 1) * wsize_4h if w < N_WINDOWS - 1 else total_4h
            regime_slice = [btc_closes[i] > btc_ema200[i] if btc_ema200[i] > 0 else False for i in range(s4, e4)]
            e1_net, e1_n = run_e1_dip_4h(candles_4h[s4:e4], regime_slice)
            
            # E2 (1H)
            s1 = w * wsize_1h; e1 = (w + 1) * wsize_1h if w < N_WINDOWS - 1 else total_1h
            e2_net, e2_n = run_e2_bb_1h(candles_1h[s1:e1])
            
            # E3 (Buy & Hold 4H)
            bh_start = candles_4h[s4]["c"]
            bh_end = candles_4h[e4 - 1]["c"]
            bh_net = ((bh_end - bh_start) / bh_start * 100)
            
            sym_res["E1"].append({"n": e1_n, "net": round(e1_net, 2)})
            sym_res["E2"].append({"n": e2_n, "net": round(e2_net, 2)})
            sym_res["E3"].append({"net": round(bh_net, 2)})
            
        results[sym] = sym_res
        print(f"  E1 (4H DIP): W1-W4 Net: {[r['net'] for r in sym_res['E1']]}")
        print(f"  E2 (1H BB):  W1-W4 Net: {[r['net'] for r in sym_res['E2']]}")
        print(f"  E3 (B&H 4H): W1-W4 Net: {[r['net'] for r in sym_res['E3']]}")

    with open("final_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved: final_test_results.json")

if __name__ == "__main__":
    main()
