#!/usr/bin/env python3
# backtest_m14_grid_v3.py — M14-Grid v3 (3 optimizations applied)
# 1. Position size 2% (was 5%)
# 2. Portfolio kill-switch at 10% drawdown
# 3. Multi-timeframe ADX (1h instead of 5m)

import requests, time, hashlib

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
INTERVAL = "5m"
ADX_INTERVAL = "1h"
FETCH_DAYS = 730
WINDOW_SIZE = 25920
MAKER_FEE = 0.0002
SLIPPAGE = 0.001
FILL_RATE = 0.85
CAPITAL_PER_ASSET = 1000.0
POSITION_PCT = 0.02  # تغییر ۱: 2% (was 5%)
CAP_PER_GRID = CAPITAL_PER_ASSET * POSITION_PCT
ADX_THRESHOLD = 20.0
RANGE_LOOKBACK = 8640
PORTFOLIO_KILL_DD = 0.10  # تغییر ۲: 10% kill-switch

def should_fill(candle_time, price_level):
    h = hashlib.md5(f"{candle_time}_{int(price_level*100)}".encode()).hexdigest()
    return int(h[:8], 16) % 100 < (FILL_RATE * 100)

def fetch_klines(symbol, interval="5m", days=730, limit=1000):
    all_candles = []
    end_time = int(time.time() * 1000)
    candles_per_day = 24 * 12 if interval == "5m" else 24
    target = days * candles_per_day
    
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

def simulate_quarter(all_data, adx_map, start, end):
    states = {}
    for sym, data in all_data.items():
        candles = data["candles"]
        range_start = max(0, start - RANGE_LOOKBACK)
        if len(candles[range_start:start]) < 100: continue
        
        high_30d = max(c['h'] for c in candles[range_start:start])
        low_30d = min(c['l'] for c in candles[range_start:start])
        if low_30d == 0: continue
        
        base_price = candles[start]['c']
        if base_price == 0: continue
        
        avg_atr = sum(data["atr"][range_start:start]) / len(data["atr"][range_start:start])
        spacing = max(2.5 * avg_atr, base_price * 0.004)
        
        levels = []
        level = low_30d
        while level <= high_30d:
            levels.append({"price": level, "status": "empty", "qty": 0})
            level += spacing
        if not levels: continue
        
        cash = CAPITAL_PER_ASSET
        inventory = []
        for g in levels:
            if g["price"] < base_price and cash >= CAP_PER_GRID:
                qty = CAP_PER_GRID / g["price"]
                cash -= CAP_PER_GRID
                g["status"] = "filled"
                g["qty"] = qty
                inventory.append(g)
        
        states[sym] = {
            "cash": cash, "inventory": inventory, "levels": levels,
            "spacing": spacing, "trades": 0, "skipped": 0,
            "peak_eq": CAPITAL_PER_ASSET, "max_dd": 0.0
        }
    
    if not states: return None
    
    initial_portfolio = CAPITAL_PER_ASSET * len(states)
    peak_portfolio = initial_portfolio
    killed = False
    
    for i in range(start, end):
        for sym, state in states.items():
            if killed: break
            
            c = all_data[sym]["candles"][i]
            low, high = c['l'], c['h']
            
            # تغییر ۳: ADX از تایم‌فریم ۱ ساعته
            hour_time = (c['t'] // 3600000) * 3600000
            current_adx = adx_map.get(hour_time, 100)  # default = don't trade
            
            # Sell
            for g in list(state["inventory"]):
                target_price = g["price"] + state["spacing"]
                if target_price <= high and should_fill(c['t'], target_price):
                    actual_price = target_price * (1 - SLIPPAGE)
                    proceeds = g["qty"] * actual_price
                    state["cash"] += (proceeds - (proceeds * MAKER_FEE))
                    state["trades"] += 1
                    state["inventory"].remove(g)
                    g["status"] = "empty"
                    g["qty"] = 0
            
            # Buy (only if 1h ADX < threshold)
            if current_adx < ADX_THRESHOLD:
                for g in state["levels"]:
                    if g["status"] == "empty" and g["price"] >= low and g["price"] <= high and state["cash"] >= CAP_PER_GRID:
                        if should_fill(c['t'], g["price"]):
                            actual_price = g["price"] * (1 + SLIPPAGE)
                            qty = CAP_PER_GRID / actual_price
                            state["cash"] -= CAP_PER_GRID
                            g["status"] = "filled"
                            g["qty"] = qty
                            state["inventory"].append(g)
                        else:
                            state["skipped"] += 1
        
        # Update per-asset equity
        for sym, state in states.items():
            c = all_data[sym]["candles"][i]
            val = state["cash"] + sum(g["qty"] * c['c'] for g in state["inventory"])
            if val > state["peak_eq"]: state["peak_eq"] = val
            dd = (state["peak_eq"] - val) / state["peak_eq"] * 100
            if dd > state["max_dd"]: state["max_dd"] = dd
        
        # تغییر ۲: Portfolio kill-switch (check hourly to save compute)
        if i % 12 == 0:
            portfolio_value = sum(
                state["cash"] + sum(g["qty"] * all_data[sym]["candles"][i]['c'] for g in state["inventory"])
                for sym, state in states.items()
            )
            if portfolio_value > peak_portfolio:
                peak_portfolio = portfolio_value
            if portfolio_value < peak_portfolio * (1 - PORTFOLIO_KILL_DD):
                killed = True
                break
    
    portfolio_net = 0
    max_dd = 0
    total_trades = 0
    total_skipped = 0
    
    end_idx = end - 1
    for sym, state in states.items():
        if end_idx >= len(all_data[sym]["candles"]):
            end_idx = len(all_data[sym]["candles"]) - 1
        
    for sym, state in states.items():
        final_c = all_data[sym]["candles"][end_idx]['c']
        final_val = state["cash"] + sum(g["qty"] * final_c for g in state["inventory"])
        net_pct = ((final_val/CAPITAL_PER_ASSET) - 1) * 100
        portfolio_net += net_pct
        total_trades += state["trades"]
        total_skipped += state["skipped"]
        if state["max_dd"] > max_dd: max_dd = state["max_dd"]
    
    if states:
        portfolio_net /= len(states)
    
    return {
        "net_pct": portfolio_net,
        "max_dd": max_dd,
        "trades": total_trades,
        "skipped": total_skipped,
        "killed": killed
    }

def main():
    print(f"=== M14-Grid v3 (3 Optimizations) ===\n")
    print(f"1. Position: {POSITION_PCT*100}% per grid (was 5%)")
    print(f"2. Kill-switch: {PORTFOLIO_KILL_DD*100}% portfolio DD")
    print(f"3. ADX filter: {ADX_INTERVAL} timeframe\n")
    
    all_data = {}
    adx_map = {}
    
    for sym in SYMBOLS:
        print(f"Fetching {sym} 5m and 1h data...")
        candles_5m = fetch_klines(sym, "5m", FETCH_DAYS)
        candles_1h = fetch_klines(sym, "1h", FETCH_DAYS)
        
        if len(candles_5m) < RANGE_LOOKBACK + WINDOW_SIZE:
            print(f"  Not enough 5m data\n")
            continue
        
        atr = calc_atr(candles_5m, 14)
        
        adx_1h = calc_adx(candles_1h, 14)
        sym_adx_map = {candles_1h[i]['t']: adx_1h[i] for i in range(len(candles_1h))}
        adx_map.update(sym_adx_map)
        
        all_data[sym] = {"candles": candles_5m, "atr": atr, "len": len(candles_5m)}
        print(f"  5m: {len(candles_5m)} | 1h: {len(candles_1h)}\n")
    
    if not all_data:
        print("No data available")
        return
    
    min_len = min(d["len"] for d in all_data.values())
    n_windows = min((min_len - RANGE_LOOKBACK) // WINDOW_SIZE, 8)
    
    print(f"\n{'Qtr':<5} | {'Portfolio Net%':>15} | {'MaxDD%':>10} | {'Trades':>8} | {'Skipped':>8} | {'Killed':>8}")
    print("-" * 80)
    
    pos_wins = 0
    total_net = 0
    worst_dd = 0
    
    for w in range(n_windows):
        start = RANGE_LOOKBACK + (w * WINDOW_SIZE)
        end = start + WINDOW_SIZE
        if end > min_len: 
            end = min_len
            if end - start < 100: break
        
        res = simulate_quarter(all_data, adx_map, start, end)
        if not res: continue
        
        if res["net_pct"] > 0: pos_wins += 1
        total_net += res["net_pct"]
        if res["max_dd"] > worst_dd: worst_dd = res["max_dd"]
        
        killed_str = "YES" if res["killed"] else "no"
        print(f"Q{w+1:<4} | {res['net_pct']:>+14.2f}% | {res['max_dd']:>9.2f}% | {res['trades']:>8} | {res['skipped']:>8} | {killed_str:>8}")
    
    print("-" * 80)
    verdict = "FAILED"
    if pos_wins >= 5 and total_net > 15 and worst_dd < 15:
        verdict = "PASSED"
    elif pos_wins >= 4:
        verdict = "MARGINAL"
    
    print(f"\n-> {pos_wins}/{n_windows} Positive Quarters")
    print(f"-> Cumulative: {total_net:+.2f}%")
    print(f"-> Worst MaxDD: {worst_dd:.2f}%")
    print(f"-> VERDICT: {verdict}")
    
    if verdict == "PASSED":
        print("\n🎉 M14-Grid v3 PASSED! Ready for Paper Trading.")
    elif verdict == "FAILED":
        print("\n❌ M14-Grid v3 FAILED. Strategy is archived permanently.")

if __name__ == "__main__":
    main()
