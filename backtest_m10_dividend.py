#!/usr/bin/env python3
# backtest_m10_dividend.py — Monthly 0.5% BTC Sale to USDT (FIXED timestamp bug)

import requests, time
from datetime import datetime, timezone

INITIAL_CAPITAL = 1000000000.0
FEE = 0.006
MONTHLY_SELL_PCT = 0.005
MAX_CUMULATIVE_SELL = 0.50
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
                    # FIXED: Wallex returns seconds, not milliseconds
                    candles.append({"t": int(data['t'][i]), "c": c})
        except: pass
        current = to_ts
        time.sleep(0.3)
    unique = {c['t']: c for c in candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

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

    cash = INITIAL_CAPITAL
    btc = 0.0
    usdt = 0.0
    original_btc = 0.0
    cumulative_sold = 0.0
    sell_count = 0
    
    # Buy phase
    for i in range(3):
        buy_amount = INITIAL_CAPITAL * (0.33 if i < 2 else 0.34)
        net_buy = buy_amount * (1 - FEE)
        btc += net_buy / candles[i]['btc']
        cash -= buy_amount
    
    original_btc = btc
    print(f"Bought {btc:.8f} BTC at avg price {INITIAL_CAPITAL/original_btc:,.0f}")
    
    last_sale_month = -1
    
    for i in range(3, len(candles)):
        # FIXED: use t directly (seconds), not /1000
        dt = datetime.fromtimestamp(candles[i]['t'], tz=timezone.utc)
        current_month = dt.year * 12 + dt.month
        
        if current_month > last_sale_month:
            last_sale_month = current_month
            
            if cumulative_sold < MAX_CUMULATIVE_SELL and btc > 0:
                sell_btc = btc * MONTHLY_SELL_PCT
                sell_btc = min(sell_btc, original_btc * (MAX_CUMULATIVE_SELL - cumulative_sold))
                
                if sell_btc > 0:
                    gross = sell_btc * candles[i]['btc']
                    net = gross * (1 - FEE)
                    usdt_bought = net / candles[i]['usdt']
                    usdt += usdt_bought
                    btc -= sell_btc
                    cumulative_sold += sell_btc / original_btc
                    sell_count += 1
    
    final_btc_value = btc * candles[-1]['btc']
    final_usdt_value = usdt * candles[-1]['usdt']
    final_total = cash + final_btc_value + final_usdt_value
    
    net_pct = ((final_total / INITIAL_CAPITAL) - 1) * 100
    
    bh_btc = (INITIAL_CAPITAL * (1 - FEE)) / candles[0]['btc']
    bh_final = bh_btc * candles[-1]['btc']
    bh_net = ((bh_final / INITIAL_CAPITAL) - 1) * 100
    
    monthly_income_toman = final_usdt_value / (sell_count if sell_count > 0 else 1)
    
    print("\n=== M10-Dividend Backtest (FIXED) ===")
    print(f"Initial: {INITIAL_CAPITAL:,.0f} Toman")
    print(f"Final:   {final_total:,.0f} Toman")
    print(f"  - BTC Value:  {final_btc_value:,.0f} ({(btc/original_btc)*100:.1f}% of original)")
    print(f"  - USDT Value: {final_usdt_value:,.0f}")
    print(f"  - Cash:       {cash:,.0f}")
    print(f"\nNet Return: {net_pct:+.2f}%")
    print(f"B&H Return: {bh_net:+.2f}%")
    print(f"Underperformance vs B&H: {(net_pct - bh_net):.2f}%")
    print(f"\nTotal Sales: {sell_count}")
    print(f"Total USDT Generated: {usdt:.2f} (avg {monthly_income_toman:,.0f} Toman/month)")
    print(f"Total BTC Sold: {cumulative_sold*100:.1f}% of original")

if __name__ == "__main__":
    main()
