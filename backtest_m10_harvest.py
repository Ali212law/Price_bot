#!/usr/bin/env python3
# backtest_m10_harvest.py — Test M10-HARVEST Selling Logic (Fixed Bug v2)

import requests, time

INITIAL_CAPITAL = 1000000000.0
FEE = 0.006
ATR_MULT = 3.0
SELL_STEP_PCT = 0.30
MAX_SELL_PCT = 0.60
DAYS = 1095

def fetch_wallex_daily(symbol, days=DAYS):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={symbol}&resolution=1D&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    c = float(data['c'][i])
                    if c > 100_000_000_000: c /= 10
                    candles.append({"t": int(data['t'][i]), "c": c})
        except: pass
        current = to_ts
        time.sleep(0.3)
    unique = {c['t']: c for c in candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

def calc_atr(candles, period=14):
    n = len(candles)
    atr = [0.0] * n
    if n <= period: return atr
    trs = []
    for i in range(1, n):
        tr = abs(candles[i]['btc'] - candles[i-1]['btc'])
        trs.append(tr)
        if i >= period:
            atr[i] = sum(trs[-period:]) / period
    return atr

def main():
    print("Fetching 3 years of BTC/TMN and USDT/TMN data...")
    btc_candles = fetch_wallex_daily("BTCTMN")
    usdt_candles = fetch_wallex_daily("USDTTMN")
    
    usdt_map = {c['t'] // 86400: c['c'] for c in usdt_candles}
    
    aligned = []
    for c in btc_candles:
        day = c['t'] // 86400
        if day in usdt_map:
            aligned.append({"t": c['t'], "btc": c['c'], "usdt": usdt_map[day]})
    
    candles = aligned
    print(f"Fetched {len(candles)} aligned days.")
    
    if len(candles) < 100:
        print("Not enough data.")
        return

    atr = calc_atr(candles, 14)
    
    cash_toman = INITIAL_CAPITAL
    btc_amount = 0.0
    usdt_amount = 0.0
    sold_pct = 0.0
    
    peak_price = 0.0
    sell_count = 0
    
    for i in range(14, len(candles)):
        btc_price = candles[i]['btc']
        usdt_price = candles[i]['usdt']
        current_atr = atr[i]
        
        if i < 17:
            buy_amount = INITIAL_CAPITAL * (0.33 if i < 16 else 0.34)
            fee_toman = buy_amount * FEE
            net_buy = buy_amount - fee_toman
            btc_bought = net_buy / btc_price
            btc_amount += btc_bought
            cash_toman -= buy_amount
            peak_price = btc_price
            continue
            
        if btc_price > peak_price:
            peak_price = btc_price
            
        if current_atr > 0:
            stop_price = peak_price - (ATR_MULT * current_atr)
            
            if btc_price < stop_price and sold_pct < MAX_SELL_PCT and btc_amount > 0:
                sell_btc = btc_amount * SELL_STEP_PCT
                gross_toman = sell_btc * btc_price
                fee_toman = gross_toman * FEE
                net_toman = gross_toman - fee_toman
                
                usdt_bought = net_toman / usdt_price
                usdt_amount += usdt_bought
                btc_amount -= sell_btc
                sold_pct += SELL_STEP_PCT
                sell_count += 1
                
                print(f"SELL day {i}: BTC={btc_price:,.0f} | USDT={usdt_price:,.0f} | Sold 30% ({sell_btc:.8f} BTC) -> {usdt_bought:.4f} USDT")
                peak_price = btc_price

    final_btc_price = candles[-1]['btc']
    final_usdt_price = candles[-1]['usdt']
    
    final_btc_value = btc_amount * final_btc_price
    final_usdt_value = usdt_amount * final_usdt_price
    final_total = cash_toman + final_btc_value + final_usdt_value
    
    net_pct = ((final_total / INITIAL_CAPITAL) - 1) * 100
    
    bh_btc = (INITIAL_CAPITAL * (1 - FEE)) / candles[14]['btc']
    bh_final = bh_btc * final_btc_price
    bh_net = ((bh_final / INITIAL_CAPITAL) - 1) * 100
    
    equity_curve = []
    cur_btc = 0.0
    cur_cash = INITIAL_CAPITAL
    cur_usdt = 0.0
    cur_sold = 0.0
    cur_peak_price = 0.0
    
    for i in range(14, len(candles)):
        bp = candles[i]['btc']
        up = candles[i]['usdt']
        if i < 17:
            buy = INITIAL_CAPITAL * (0.33 if i < 16 else 0.34)
            cur_btc += (buy * (1 - FEE)) / bp
            cur_cash -= buy
            cur_peak_price = bp
            equity_curve.append(cur_cash + cur_btc * bp + cur_usdt * up)
            continue
        if bp > cur_peak_price: cur_peak_price = bp
        if atr[i] > 0 and bp < (cur_peak_price - ATR_MULT * atr[i]) and cur_sold < MAX_SELL_PCT and cur_btc > 0:
            sell_btc = cur_btc * SELL_STEP_PCT
            gross = sell_btc * bp
            net = gross * (1 - FEE)
            cur_usdt += net / up
            cur_btc -= sell_btc
            cur_sold += SELL_STEP_PCT
            cur_peak_price = bp
        equity_curve.append(cur_cash + cur_btc * bp + cur_usdt * up)
    
    peak_eq = 0.0
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd
    
    print("\n=== M10-HARVEST Backtest (CORRECTED) ===")
    print(f"Initial: {INITIAL_CAPITAL:,.0f} Toman")
    print(f"Final:   {final_total:,.0f} Toman")
    print(f"  - BTC Value:  {final_btc_value:,.0f}")
    print(f"  - USDT Value: {final_usdt_value:,.0f}")
    print(f"  - Cash:       {cash_toman:,.0f}")
    print(f"Net Return: {net_pct:+.2f}%")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Total Sells: {sell_count} (Limit: <12)")
    print(f"Toman Sold: 0 (Rule: 0)")
    print(f"B&H Return: {bh_net:+.2f}%")
    
    return_ratio = net_pct / bh_net if bh_net > 0 else 0
    passed = (net_pct > 0) and (sell_count < 12) and (return_ratio >= 0.90)
    
    print(f"\nReturn vs B&H ratio: {return_ratio*100:.1f}% (Need >= 90%)")
    print(f"VERDICT: {'PASSED' if passed else 'FAILED'}")

if __name__ == "__main__":
    main()
