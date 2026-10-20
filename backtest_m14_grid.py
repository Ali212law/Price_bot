#!/usr/bin/env python3
# backtest_m14_grid.py — Multi-Year Grid Test with Realistic Fill Rate & Slippage
import requests, time, hashlib

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
INTERVAL = "5m"
FETCH_DAYS = 730  # 2 years
WINDOW_SIZE = 25920  # 90 days
MAKER_FEE = 0.0002
SLIPPAGE = 0.001  # 0.1% per side
FILL_RATE = 0.85
CAPITAL_PER_ASSET = 1000.0
CAP_PER_GRID = 50.0
ADX_THRESHOLD = 20.0
RANGE_LOOKBACK = 8640

def should_fill(candle_time, price_level):
    h = hashlib.md5(f"{candle_time}_{int(price_level*100)}".encode()).hexdigest()
    return int(h[:8], 16) % 100 < (FILL_RATE * 100)

def fetch_binance_vision(symbol, interval="5m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = FETCH_DAYS * 24 * 12
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
        time.sleep(0.05)
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

def simulate_window(candles, atr, adx, start, end):
    if end - start < 100: return None
    range_start = max(0, start - RANGE_LOOKBACK)
    if len(candles[range_start:start]) < 100: return None
    
    high_30d = max(c['h'] for c in candles[range_start:start])
    low_30d = min(c['l'] for c in candles[range_start:start])
    if low_30d == 0: return None
    
    base_price = candles[start]['c']
    if base_price == 0: return None
    
    avg_atr = sum(atr[range_start:start]) / len(atr[range_start:start])
    spacing = max(2.5 * avg_atr, base_price * 0.004)
    
    levels = []
    level = low_30d
    while level <= high_30d:
        levels.append({"price": level, "status": "empty", "qty": 0})
        level += spacing
    if not levels: return None
    
    cash = CAPITAL_PER_ASSET
    inventory = []
    trades = 0
    skipped = 0
    
    for g in levels:
        if g["price"] < base_price and cash >= CAP_PER_GRID:
            qty = CAP_PER_GRID / g["price"]
            cash -= CAP_PER_GRID
            g["status"] = "filled"
            g["qty"] = qty
            inventory.append(g)
    
    peak_eq = CAPITAL_PER_ASSET
    max_dd = 0.0
    
    for i in range(start, end):
        c = candles[i]
        low, high = c['l'], c['h']
        current_adx = adx[i] if i < len(adx) else 0
        
        for g in list(inventory):
            target_price = g["price"] + spacing
            if target_price <= high:
                if should_fill(c['t'], target_price):
                    actual_price = target_price * (1 - SLIPPAGE)
                    proceeds = g["qty"] * actual_price
                    cash += (proceeds - (proceeds * MAKER_FEE))
                    trades += 1
                    inventory.remove(g)
                    g["status"] = "empty"
                    g["qty"] = 0
                else:
                    skipped += 1
        
        if current_adx < ADX_THRESHOLD:
            for g in levels:
                if g["status"] == "empty" and g["price"] >= low and g["price"] <= high and cash >= CAP_PER_GRID:
                    if should_fill(c['t'], g["price"]):
                        actual_price = g["price"] * (1 + SLIPPAGE)
                        qty = CAP_PER_GRID / actual_price
                        cash -= CAP_PER_GRID
                        g["status"] = "filled"
                        g["qty"] = qty
                        inventory.append(g)
                    else:
                        skipped += 1
        
        val = cash + sum(g["qty"] * c['c'] for g in inventory)
        if val > peak_eq: peak_eq = val
        dd = (peak_eq - val) / peak_eq * 100
        if dd > max_dd: max_dd = dd
    
    final_val = cash + sum(g["qty"] * candles[end-1]['c'] for g in inventory)
    net_pct = ((final_val/CAPITAL_PER_ASSET) - 1) * 100
    
    bh_start = candles[start]['c']
    bh_end = candles[end-1]['c']
    bh_pct = ((bh_end/bh_start) - 1) * 100 if bh_start > 0 else 0
    
    return {"net_pct": net_pct, "max_dd": max_dd, "trades": trades, "skipped": skipped, "bh_pct": bh_pct}

def main():
    print(f"=== M14-Grid Multi-Year Test (2 years, 8 quarters) ===\n")
    print(f"Settings: Fill Rate={FILL_RATE*100}%, Slippage={SLIPPAGE*100}%, Fee={MAKER_FEE*100}%\n")
    
    all_data = {}
    for sym in SYMBOLS:
        print(f"Fetching {sym} ({FETCH_DAYS} days)...")
        candles = fetch_binance_vision(sym)
        if len(candles) < RANGE_LOOKBACK + WINDOW_SIZE:
            print(f"Not enough data for {sym}\n")
            continue
        atr = calc_atr(candles, 14)
        adx = calc_adx(candles, 14)
        all_data[sym] = {"candles": candles, "atr": atr, "adx": adx, "len": len(candles)}
        print(f"  -> {len(candles)} candles\n")
    
    if not all_data: 
        print("No data available")
        return
    
    min_len = min(d["len"] for d in all_data.values())
    n_windows = min((min_len - RANGE_LOOKBACK) // WINDOW_SIZE, 8)
    
    print(f"\n{'Qtr':<5} | {'Portfolio Net%':>15} | {'MaxDD%':>10} | {'B&H Avg%':>10} | {'Trades':>8} | {'Skipped':>8}")
    print("-" * 75)
    
    pos_wins = 0
    total_net = 0
    worst_dd = 0
    
    for w in range(n_windows):
        start = RANGE_LOOKBACK + (w * WINDOW_SIZE)
        end = start + WINDOW_SIZE
        if end > min_len: break
        
        results = []
        bh_results = []
        total_trades = 0
        total_skipped = 0
        
        for sym, data in all_data.items():
            res = simulate_window(data["candles"], data["atr"], data["adx"], start, end)
            if res:
                results.append(res)
                bh_results.append(res["bh_pct"])
                total_trades += res["trades"]
                total_skipped += res["skipped"]
        
        if not results: continue
        
        port_net = sum(r["net_pct"] for r in results) / len(results)
        port_dd = max(r["max_dd"] for r in results)
        avg_bh = sum(bh_results) / len(bh_results)
        
        if port_net > 0: pos_wins += 1
        total_net += port_net
        if port_dd > worst_dd: worst_dd = port_dd
        
        print(f"Q{w+1:<4} | {port_net:>+14.2f}% | {port_dd:>9.2f}% | {avg_bh:>+9.2f}% | {total_trades:>8} | {total_skipped:>8}")
    
    print("-" * 75)
    verdict = "PASSED" if pos_wins >= 6 else ("MARGINAL" if pos_wins >= 4 else "FAILED")
    print(f"\n-> {pos_wins}/{n_windows} Positive Quarters")
    print(f"-> Cumulative: {total_net:+.2f}%")
    print(f"-> Worst MaxDD: {worst_dd:.2f}%")
    print(f"-> VERDICT: {verdict}")

if __name__ == "__main__":
    main()
