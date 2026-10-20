#!/usr/bin/env python3
# backtest_m14_grid.py — M14-Grid with ADX Regime Filter (D-53)

import requests, time

SYMBOLS = ["SOLUSDT", "DOGEUSDT", "AVAXUSDT"]
INTERVAL = "5m"
DAYS = 30
MAKER_FEE = 0.0002
GRID_MULTIPLIER = 2.5
CAPITAL = 1000.0
CAP_PER_GRID = 50.0
RANGE_PCT = 0.10
ADX_THRESHOLD = 20.0 # فقط در رنج معامله کن

def fetch_binance_vision(symbol, interval="5m", limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = DAYS * 24 * 12
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

def simulate_grid(candles, atr_series, adx_series, symbol):
    base_price = candles[20]['c']
    avg_atr = sum(atr_series[-1000:]) / 1000
    spacing = max(GRID_MULTIPLIER * avg_atr, base_price * 0.004)
    
    lower = base_price * (1 - RANGE_PCT)
    upper = base_price * (1 + RANGE_PCT)
    
    levels = []
    level = lower
    while level <= upper:
        levels.append({"price": level, "status": "empty", "qty": 0})
        level += spacing
        
    cash = CAPITAL
    inventory = []
    trades = 0
    fees = 0.0
    
    # Initial buys
    for g in levels:
        if g["price"] < base_price and cash >= CAP_PER_GRID:
            qty = CAP_PER_GRID / g["price"]
            cash -= CAP_PER_GRID
            fees += CAP_PER_GRID * MAKER_FEE
            g["status"] = "filled"
            g["qty"] = qty
            inventory.append(g)
            
    peak_equity = CAPITAL
    max_dd = 0.0
    
    for i in range(21, len(candles)):
        c = candles[i]
        low, high = c['l'], c['h']
        current_adx = adx_series[i]
        
        # Check Sell (Always allowed)
        for g in list(inventory):
            if g["price"] + spacing <= high:
                proceeds = g["qty"] * (g["price"] + spacing)
                fee = proceeds * MAKER_FEE
                cash += (proceeds - fee)
                fees += fee
                trades += 1
                inventory.remove(g)
                g["status"] = "empty"
                g["qty"] = 0
        
        # Check Buy (Only if ADX < 20)
        if current_adx < ADX_THRESHOLD:
            for g in levels:
                if g["status"] == "empty" and g["price"] >= low and g["price"] <= high and cash >= CAP_PER_GRID:
                    qty = CAP_PER_GRID / g["price"]
                    cash -= CAP_PER_GRID
                    fees += CAP_PER_GRID * MAKER_FEE
                    g["status"] = "filled"
                    g["qty"] = qty
                    inventory.append(g)
                
        current_value = cash + sum(g["qty"] * c['c'] for g in inventory)
        if current_value > peak_equity: peak_equity = current_value
        dd = (peak_equity - current_value) / peak_equity * 100
        if dd > max_dd: max_dd = dd
        
    final_value = cash + sum(g["qty"] * candles[-1]['c'] for g in inventory)
    net_profit = final_value - CAPITAL
    return {"net": net_profit, "net_pct": (net_profit/CAPITAL)*100, "max_dd": max_dd, "trades": trades, "fees": fees}

def main():
    print(f"=== M14-Grid + ADX Filter (Threshold: {ADX_THRESHOLD}) ===")
    for symbol in SYMBOLS:
        candles = fetch_binance_vision(symbol, INTERVAL)
        if len(candles) < 1000: continue
        atr = calc_atr(candles, 14)
        adx = calc_adx(candles, 14)
        res = simulate_grid(candles, atr, adx, symbol)
        print(f"\n--- {symbol} ---")
        print(f"Net Profit: ${res['net']:.2f} ({res['net_pct']:+.2f}%)")
        print(f"Max Drawdown: {res['max_dd']:.2f}%")
        print(f"Total Trades: {res['trades']}")
        print(f"Total Fees Paid: ${res['fees']:.2f}")

if __name__ == "__main__":
    main()
