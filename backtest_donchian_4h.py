#!/usr/bin/env python3
# backtest_donchian_4h.py — Challenger 1: Donchian(50) + Volume Filter on 4H (FIXED)

import requests, time

SYMBOLS = ["ETHUSDT", "SOLUSDT", "SUIUSDT"]
INTERVAL = "4h"
FETCH_DAYS = 730
MAKER_FEE = 0.0002
SLIPPAGE = 0.001
TOTAL_FEE = MAKER_FEE + SLIPPAGE
CAPITAL_PER_ASSET = 1000.0
RISK_PER_TRADE = 0.02

DONCHIAN_PERIOD = 50
ATR_MULT = 2.0
VOL_LOOKBACK = 20

def fetch_klines(symbol, interval, days):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = days * 6
    while len(all_candles) < target:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&endTime={end_time}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                        "l": float(k[3]), "c": float(k[4]), "v": float(k[5])
                    })
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
        tr = max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - candles[i-1]['c']), abs(candles[i]['l'] - candles[i-1]['c']))
        trs.append(tr)
        if i >= period:
            atr[i] = sum(trs[-period:]) / period
    return atr

def run_donchian(candles, atr):
    cash = CAPITAL_PER_ASSET
    position = None
    trades = 0
    wins = 0
    equity_peak = CAPITAL_PER_ASSET
    max_dd = 0.0

    for i in range(DONCHIAN_PERIOD + VOL_LOOKBACK, len(candles)):
        c = candles[i]
        
        if position is None:
            upper_band = max(x['h'] for x in candles[i-DONCHIAN_PERIOD:i])
            avg_vol = sum(x['v'] for x in candles[i-VOL_LOOKBACK:i]) / VOL_LOOKBACK
            
            if c['c'] > upper_band and c['v'] > avg_vol * 1.5:
                if atr[i] > 0:
                    sl_dist = ATR_MULT * atr[i]
                    sl_price = c['c'] - sl_dist
                    
                    equity = cash 
                    risk_amount = equity * RISK_PER_TRADE
                    qty = risk_amount / sl_dist
                    
                    # FIXED: Check if we have enough cash to buy this qty
                    cost = qty * c['c']
                    fee = cost * TOTAL_FEE
                    
                    if cost + fee > cash:
                        # Not enough cash, reduce qty to max affordable
                        qty = cash / (c['c'] * (1 + TOTAL_FEE))
                        cost = qty * c['c']
                        fee = cost * TOTAL_FEE
                        
                    cash -= (cost + fee)
                    position = {"entry": c['c'], "sl": sl_price, "qty": qty, "idx": i}
                    trades += 1
        else:
            if c['l'] <= position['sl']:
                gross = position['qty'] * position['sl']
                exit_fee = gross * TOTAL_FEE
                cash += (gross - exit_fee)
                
                if position['sl'] > position['entry']: wins += 1
                position = None
            else:
                new_sl = c['c'] - (ATR_MULT * atr[i])
                if new_sl > position['sl']:
                    position['sl'] = new_sl

        # Mark to market (FIXED: Include cash + position value)
        val = cash + (position['qty'] * c['c'] if position else 0)
        if val > equity_peak: equity_peak = val
        dd = (equity_peak - val) / equity_peak * 100
        if dd > max_dd: max_dd = dd

    final_price = candles[-1]['c']
    final_val = cash + (position['qty'] * final_price if position else 0)
    net_pct = ((final_val / CAPITAL_PER_ASSET) - 1) * 100
    wr = (wins / trades * 100) if trades > 0 else 0

    return {"net_pct": net_pct, "max_dd": max_dd, "trades": trades, "wr": wr}

def main():
    print("=== Challenger 1: Donchian(50) + Volume (4H) - FIXED ===\n")
    
    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...")
        candles = fetch_klines(symbol, INTERVAL, FETCH_DAYS)
        if len(candles) < DONCHIAN_PERIOD: continue
        print(f"  {len(candles)} candles.")
        
        atr = calc_atr(candles, 14)
        res = run_donchian(candles, atr)
        
        print(f"  Net: {res['net_pct']:+.2f}% | MaxDD: {res['max_dd']:.2f}% | Trades: {res['trades']} | WR: {res['wr']:.1f}%\n")

if __name__ == "__main__":
    main()
