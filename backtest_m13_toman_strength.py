#!/usr/bin/env python3
# backtest_m13_toman_strength.py — Buy when Toman strengthens (USDT drops)

import requests, time

INITIAL_CAPITAL = 1000000000.0 # 1 Billion Toman

def fetch_wallex_daily(symbol, days=1095):
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

def main():
    print("Fetching BTC/TMN and USDT/TMN data (3 years)...")
    btc = fetch_wallex_daily("BTCTMN")
    usdt = fetch_wallex_daily("USDTTMN")
    
    usdt_dict = {c['t'] // 86400: c['c'] for c in usdt}
    
    data = []
    for b in btc:
        day = b['t'] // 86400
        if day in usdt_dict:
            data.append({"t": b['t'], "btc": b['c'], "usdt": usdt_dict[day]})
            
    if len(data) < 100:
        print("Not enough data.")
        return

    # Buy & Hold Benchmark
    bh_btc = INITIAL_CAPITAL / data[0]['btc']
    bh_value = bh_btc * data[-1]['btc']
    
    # M13 Strategy (Buy when USDT drops > 1.5% in a day)
    strat_capital = INITIAL_CAPITAL
    strat_btc = 0.0
    strat_trades = 0
    
    for i in range(1, len(data)):
        prev_usdt = data[i-1]['usdt']
        curr_usdt = data[i]['usdt']
        curr_btc = data[i]['btc']
        
        # Calculate daily Toman change (USDT change)
        usdt_change_pct = ((curr_usdt - prev_usdt) / prev_usdt) * 100
        
        # If Toman strengthens (USDT drops > 1.5%)
        if usdt_change_pct < -1.5:
            buy_amount = strat_capital * 0.20
            if buy_amount > 1000000: # Minimum buy threshold
                strat_btc += buy_amount / curr_btc
                strat_capital -= buy_amount
                strat_trades += 1

    strat_value = strat_btc * data[-1]['btc'] + strat_capital
    
    print("\n=== M13: Toman Strength Detector vs Buy & Hold (3 Years) ===")
    print(f"Start Price: {data[0]['btc']:,.0f} | End Price: {data[-1]['btc']:,.0f}")
    print(f"1. Buy & Hold Value: {bh_value:,.0f} Toman ({(bh_value/INITIAL_CAPITAL-1)*100:.1f}%)")
    print(f"2. Toman Strength Value: {strat_value:,.0f} Toman ({(strat_value/INITIAL_CAPITAL-1)*100:.1f}%) | Buys: {strat_trades}")

if __name__ == "__main__":
    main()
