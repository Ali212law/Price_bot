#!/usr/bin/env python3
# backtest_m12_toman_crash.py — Toman Crash Detector vs Buy & Hold
import requests, json, time
from datetime import datetime, timezone

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

    # Buy & Hold Strategy (Buy all on day 1)
    bh_btc = INITIAL_CAPITAL / data[0]['btc']
    bh_value = bh_btc * data[-1]['btc']
    
    # Toman Crash Detector (M12)
    crash_capital = INITIAL_CAPITAL
    crash_btc = 0.0
    crash_trades = 0
    
    for i in range(1, len(data)):
        prev_usdt = data[i-1]['usdt']
        curr_usdt = data[i]['usdt']
        curr_btc = data[i]['btc']
        
        # Calculate daily Toman depreciation
        usdt_change_pct = ((curr_usdt - prev_usdt) / prev_usdt) * 100
        
        # If Toman crashes (USDT goes up > 1.5% in a day)
        if usdt_change_pct > 1.5:
            # Buy 20% of remaining cash
            buy_amount = crash_capital * 0.20
            crash_btc += buy_amount / curr_btc
            crash_capital -= buy_amount
            crash_trades += 1

    crash_value = crash_btc * data[-1]['btc'] + crash_capital
    
    print("\n=== M12: Toman Crash Detector vs Buy & Hold (3 Years) ===")
    print(f"Start Price: {data[0]['btc']:,.0f} | End Price: {data[-1]['btc']:,.0f}")
    print(f"Buy & Hold Value: {bh_value:,.0f} Toman ({(bh_value/INITIAL_CAPITAL-1)*100:.1f}%)")
    print(f"Crash Detector Value: {crash_value:,.0f} Toman ({(crash_value/INITIAL_CAPITAL-1)*100:.1f}%) | Buys: {crash_trades}")

if __name__ == "__main__":
    main()
