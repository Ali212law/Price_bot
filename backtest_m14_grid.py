#!/usr/bin/env python3
# backtest_m14_grid.py — Adaptive Multi-Asset Grid (v2)
# Design: Multi-Asset Portfolio + ADX Filter + Dynamic Range

import requests, time

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
INTERVAL = "5m"
TOTAL_DAYS = 120
MAKER_FEE = 0.0002
GRID_MULTIPLIER = 2.5
CAPITAL_PER_ASSET = 1000.0
CAP_PER_GRID = 50.0
ADX_THRESHOLD = 20.0
RANGE_LOOKBACK = 8640 # 30 days of 5m candles

def fetch_binance_vision(symbol, interval="5m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = TOTAL_DAYS * 24 * 12
    while len(all_candles) < target:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&endTime={end_time}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])})
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.2)
    unique = {c['t']: c for c in all_candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

def calc_atr(candles, period=14):
    n = len(candles)
    atr = [0.0] * n
    if n <= period: return atr
    trs = []
    for i in range(1, n):
        trs.append(max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - candles[i-1]['c']), abs(candles[i]['l'] - candles[i-1]['c'])))
        if i >= period: atr[i] = sum(trs[-period:]) / period
    return atr

def calc_adx(candles, period=14):
    n = len(candles)
    adx = [0.0] * n
    if n < period * 2: return adx
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        h, l, pc = candles[i]['h'], candles[i]['l'], candles[i-1]['c']
        ph, pl = candles[i-1]['h'], candles[i-1]['l']
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, down = h - ph, pl - l
        plus_dm.append(up if (up > down and up > 0) else 0)
        minus_dm.append(down if (down > up and down > 0) else 0)
    smooth_tr = sum(tr_list[:period])
    smooth_plus = sum(plus_dm[:period])
    smooth_minus = sum(minus_dm[:period])
    dx_list = []
    for i in range(period, len(tr_list)):
        smooth_tr = smooth_tr - (smooth_tr / period) + tr_list[i]
        smooth_plus = smooth_plus - (smooth_plus / period) + plus_dm[i]
        smooth_minus = smooth_minus - (smooth_minus / period) + minus_dm[i]
        pdi = (smooth_plus / smooth_tr) * 100 if smooth_tr > 0 else 0
        mdi = (smooth_minus / smooth_tr) * 100 if smooth_tr > 0 else 0
        dx = (abs(pdi - mdi) / (pdi + mdi)) * 100 if (pdi + mdi) > 0 else 0
        dx_list.append(dx)
    if len(dx_list) >= period:
        adx_val = sum(dx_list[:period]) / period
        adx[period*2-1] = adx_val
        for i in range(period, len(dx_list)):
            adx_val = ((adx_val * (period - 1)) + dx_list[i]) / period
            adx[i + period] = adx_val
    return adx

def simulate_window(symbol, candles, atr, adx, start, end):
    if end - start < RANGE_LOOKBACK + 100: return None
    
    # Dynamic range from last 30 days
    window_for_range = candles[start:start+RANGE_LOOKBACK]
    high_30d = max(c['h'] for c in window_for_range)
    low_30d = min(c['l'] for c in window_for_range)
    
    if low_30d == 0: return None
    
    base_price = candles[start+RANGE_LOOKBACK]['c']
    avg_atr = sum(atr[start:start+RANGE_LOOKBACK]) / RANGE_LOOKBACK
    spacing = max(GRID_MULTIPLIER * avg_atr, base_price * 0.004)
    
    # Dynamic levels
    levels = []
    level = low_30d
    while level <= high_30d:
        levels.append({"price": level, "status": "empty", "qty": 0})
        level += spacing
    
    if not levels: return None
    
    cash = CAPITAL_PER_ASSET
    inventory = []
    trades = 0
    
    # Initial buys for levels below current price
    for g in levels:
        if g["price"] < base_price and cash >= CAP_PER_GRID:
            qty = CAP_PER_GRID / g["price"]
            cash -= CAP_PER_GRID
            g["status"] = "filled"
            g["qty"] = qty
            inventory.append(g)
    
    peak_eq = CAPITAL_PER_ASSET
    max_dd = 0.0
    
    for i in range(start+RANGE_LOOKBACK, end):
        c = candles[i]
        low, high = c['l'], c['h']
        current_adx = adx[i] if i < len(adx) else 0
        
        # Sell
        for g in list(inventory):
            if g["price"] + spacing <= high:
                proceeds = g["qty"] * (g["price"] + spacing)
                cash += (proceeds - (proceeds * MAKER_FEE))
                trades += 1
                inventory.remove(g)
                g["status"] = "empty"
                g["qty"] = 0
        
        # Buy (ADX filter)
        if current_adx < ADX_THRESHOLD:
            for g in levels:
                if g["status"] == "empty" and g["price"] >= low and g["price"] <= high and cash >= CAP_PER_GRID:
                    qty = CAP_PER_GRID / g["price"]
                    cash -= CAP_PER_GRID
                    g["status"] = "filled"
                    g["qty"] = qty
                    inventory.append(g)
        
        val = cash + sum(g["qty"] * c['c'] for g in inventory)
        if val > peak_eq: peak_eq = val
        dd = (peak_eq - val) / peak_eq * 100
        if dd > max_dd: max_dd = dd
    
    final_val = cash + sum(g["qty"] * candles[end-1]['c'] for g in inventory)
    net_pct = ((final_val/CAPITAL_PER_ASSET) - 1) * 100
    return {"net_pct": net_pct, "max_dd": max_dd, "trades": trades}

def main():
    print(f"=== Adaptive Multi-Asset Grid v2 (Portfolio of {len(SYMBOLS)} assets) ===\n")
    
    all_data = {}
    for sym in SYMBOLS:
        print(f"Fetching {sym}...")
        candles = fetch_binance_vision(sym)
        if len(candles) < 1000: continue
        atr = calc_atr(candles, 14)
        adx = calc_adx(candles, 14)
        all_data[sym] = {"candles": candles, "atr": atr, "adx": adx, "len": len(candles)}
    
    if not all_data: return
    
    # 4 windows of 30 days
    window_size = 8640
    total_len = min(d["len"] for d in all_data.values())
    
    print(f"\n{'Window':<8} | {'Portfolio Net%':>15} | {'Portfolio MaxDD%':>16} | {'Total Trades':>12}")
    print("-" * 65)
    
    pos_wins = 0
    for w in range(4):
        start = w * window_size
        end = (w + 1) * window_size if w < 3 else total_len
        if end - start < 100: continue
        
        window_results = []
        total_trades = 0
        for sym, data in all_data.items():
            res = simulate_window(sym, data["candles"], data["atr"], data["adx"], start, end)
            if res:
                window_results.append(res)
                total_trades += res["trades"]
        
        if not window_results: continue
        
        # Portfolio = average of all assets
        portfolio_net = sum(r["net_pct"] for r in window_results) / len(window_results)
        portfolio_dd = max(r["max_dd"] for r in window_results)  # Worst case in portfolio
        
        if portfolio_net > 0: pos_wins += 1
        
        print(f"W{w+1:<7} | {portfolio_net:>+14.2f}% | {portfolio_dd:>15.2f}% | {total_trades:>12}")
    
    verdict = "PASSED" if pos_wins >= 3 else "FAILED"
    print(f"\n-> {pos_wins}/4 Positive Windows | PORTFOLIO VERDICT: {verdict}")
    print(f"-> This means the portfolio returned positive in {pos_wins} out of 4 windows across {len(all_data)} assets.")

if __name__ == "__main__":
    main()
