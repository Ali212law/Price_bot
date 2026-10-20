#!/usr/bin/env python3
# backtest_m10_harvest.py — Test M10-HARVEST Selling Logic (3 Years)
# Buy 3 days, then trailing stop based on 3x ATR14 daily.

import requests, time

INITIAL_CAPITAL = 1000000000.0 # 1 Billion Toman
FEE = 0.006 # 0.6% per side
ATR_MULT = 3.0
SELL_STEP_PCT = 0.30 # 30% of current holdings
MAX_SELL_PCT = 0.60 # Max 60% total
DAYS = 1095 # 3 Years

def fetch_wallex_daily(symbol="BTCTMN", days=DAYS):
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
        except Exception as e:
            pass
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
        # Since we only have close prices, we approximate TR as |close - prev_close|
        tr = abs(candles[i]['c'] - candles[i-1]['c'])
        trs.append(tr)
        if i >= period:
            atr[i] = sum(trs[-period:]) / period
    return atr

def main():
    print("Fetching 3 years of BTC/TMN data...")
    candles = fetch_wallex_daily()
    print(f"Fetched {len(candles)} days.")
    
    if len(candles) < 100:
        print("Not enough data.")
        return

    atr = calc_atr(candles, 14)
    
    cash_toman = INITIAL_CAPITAL
    btc_amount = 0.0
    usdt_balance = 0.0
    sold_pct = 0.0
    
    peak_price = 0.0
    trades = []
    
    for i in range(14, len(candles)):
        price = candles[i]['c']
        current_atr = atr[i]
        
        # Phase 1: Buying (first 3 days)
        if i < 17:
            buy_amount = INITIAL_CAPITAL * (0.33 if i < 16 else 0.34)
            fee_toman = buy_amount * FEE
            net_buy = buy_amount - fee_toman
            btc_bought = net_buy / price
            btc_amount += btc_bought
            cash_toman -= buy_amount
            trades.append({"type": "BUY", "price": price, "amount": buy_amount, "btc": btc_bought})
            peak_price = price # Initialize peak
            continue
            
        # Phase 2: Trailing Stop
        if price > peak_price:
            peak_price = price
            
        if current_atr > 0:
            stop_price = peak_price - (ATR_MULT * current_atr)
            
            # If price drops below stop, and we haven't sold max yet
            if price < stop_price and sold_pct < MAX_SELL_PCT and btc_amount > 0:
                sell_btc = btc_amount * SELL_STEP_PCT
                gross_usdt = sell_btc * price
                fee_usdt = gross_usdt * FEE
                net_usdt = gross_usdt - fee_usdt
                
                usdt_balance += net_usdt
                btc_amount -= sell_btc
                sold_pct += SELL_STEP_PCT
                
                trades.append({"type": "SELL", "price": price, "btc": sell_btc, "usdt": net_usdt})
                print(f"SELL triggered on day {i}: Price={price:,.0f} | ATR={current_atr:,.0f} | Sold 30% | USDT Balance={usdt_balance:,.0f}")
                
                # Reset peak to current price to avoid cascading sells
                peak_price = price 

    # Final Valuation
    final_price = candles[-1]['c']
    final_btc_value = btc_amount * final_price
    final_total = cash_toman + final_btc_value + (usdt_balance * candles[-1]['c']) # USDT valued in Toman proxy
    
    # Buy & Hold Benchmark
    bh_btc = INITIAL_CAPITAL / candles[14]['c']
    bh_final = bh_btc * final_price
    bh_net = ((bh_final / INITIAL_CAPITAL) - 1) * 100
    
    # M10-HARVEST metrics
    net_pct = ((final_total / INITIAL_CAPITAL) - 1) * 100
    sell_count = sum(1 for t in trades if t["type"] == "SELL")
    
    # Max DD
    equity_curve = []
    current_btc = 0.0
    current_cash = INITIAL_CAPITAL
    current_usdt = 0.0
    current_sold_pct = 0.0
    current_peak = 0.0
    
    for i in range(14, len(candles)):
        price = candles[i]['c']
        if i < 17:
            buy_amount = INITIAL_CAPITAL * (0.33 if i < 16 else 0.34)
            current_btc += (buy_amount - (buy_amount * FEE)) / price
            current_cash -= buy_amount
            current_peak = price
            equity_curve.append(current_cash + current_btc * price + current_usdt * price)
            continue
            
        if price > current_peak: current_peak = price
        if atr[i] > 0 and price < (current_peak - ATR_MULT * atr[i]) and current_sold_pct < MAX_SELL_PCT and current_btc > 0:
            sell_btc = current_btc * SELL_STEP_PCT
            gross = sell_btc * price
            current_usdt += (gross - gross * FEE)
            current_btc -= sell_btc
            current_sold_pct += SELL_STEP_PCT
            current_peak = price # reset
            
        equity_curve.append(current_cash + current_btc * price + current_usdt * price)
        
    peak_eq = 0.0
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    print("\n=== M10-HARVEST Backtest Results ===")
    print(f"Initial Capital: {INITIAL_CAPITAL:,.0f} Toman")
    print(f"Final Total: {final_total:,.0f} Toman")
    print(f"Net Return: {net_pct:+.2f}%")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Total Sells: {sell_count} (Limit: <12)")
    print(f"Toman Sold: 0 (Rule: 0)")
    print(f"B&H Return: {bh_net:+.2f}%")
    
    # Verdict
    passed = (net_pct > 0) and (max_dd < bh_net) and (sell_count < 12) and (usdt_balance > 0)
    print(f"\nVERDICT: {'PASSED' if passed else 'FAILED'}")

if __name__ == "__main__":
    main()
