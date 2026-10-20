#!/usr/bin/env python3
# backtest_m14_grid.py — Full Grid Simulation with MaxDD (D-53)
import requests, time

SYMBOLS = ["SOLUSDT", "DOGEUSDT", "AVAXUSDT"]
INTERVAL = "5m"
DAYS = 30
MAKER_FEE = 0.0002 # 0.02% per side
GRID_MULTIPLIER = 2.5
CAPITAL = 1000.0 # $1000 initial
CAP_PER_GRID = 50.0 # $50 per grid level
RANGE_PCT = 0.10 # +/- 10% range from start price

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

def simulate_grid(candles, atr_series, symbol):
    base_price = candles[20]['c']
    avg_atr = sum(atr_series[-1000:]) / 1000
    spacing = max(GRID_MULTIPLIER * avg_atr, base_price * 0.004) # Minimum 0.4% spacing
    
    lower = base_price * (1 - RANGE_PCT)
    upper = base_price * (1 + RANGE_PCT)
    
    # Initialize Grids
    levels = []
    level = lower
    while level <= upper:
        levels.append({"price": level, "status": "empty", "qty": 0})
        level += spacing
        
    # Find current level
    for i, g in enumerate(levels):
        if g["price"] > base_price:
            break
            
    cash = CAPITAL
    inventory = []
    trades = 0
    fees = 0.0
    
    # Initial Buys for levels below current price
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
        
        # Check Sell (Grids above base price that are filled)
        for g in list(inventory):
            if g["price"] + spacing <= high: # Hit target
                proceeds = g["qty"] * (g["price"] + spacing)
                fee = proceeds * MAKER_FEE
                cash += (proceeds - fee)
                fees += fee
                trades += 1
                inventory.remove(g)
                g["status"] = "empty"
                g["qty"] = 0
        
        # Check Buy (Empty grids below current price)
        for g in levels:
            if g["status"] == "empty" and g["price"] >= low and g["price"] <= high and cash >= CAP_PER_GRID:
                qty = CAP_PER_GRID / g["price"]
                cash -= CAP_PER_GRID
                fees += CAP_PER_GRID * MAKER_FEE
                g["status"] = "filled"
                g["qty"] = qty
                inventory.append(g)
                
        # Calculate Equity
        current_value = cash + sum(g["qty"] * c['c'] for g in inventory)
        if current_value > peak_equity: peak_equity = current_value
        dd = (peak_equity - current_value) / peak_equity * 100
        if dd > max_dd: max_dd = dd
        
    final_value = cash + sum(g["qty"] * candles[-1]['c'] for g in inventory)
    net_profit = final_value - CAPITAL
    return {"net": net_profit, "net_pct": (net_profit/CAPITAL)*100, "max_dd": max_dd, "trades": trades, "fees": fees}

def main():
    print("=== M14-Grid Full Simulation (30 Days) ===")
    for symbol in SYMBOLS:
        candles = fetch_binance_vision(symbol, INTERVAL)
        if len(candles) < 1000: continue
        atr = calc_atr(candles, 14)
        res = simulate_grid(candles, atr, symbol)
        print(f"\n--- {symbol} ---")
        print(f"Net Profit: ${res['net']:.2f} ({res['net_pct']:+.2f}%)")
        print(f"Max Drawdown: {res['max_dd']:.2f}%")
        print(f"Total Trades: {res['trades']}")
        print(f"Total Fees Paid: ${res['fees']:.2f}")

if __name__ == "__main__":
    main()
