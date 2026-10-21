#!/usr/bin/env python3
# verify_donchian.py — Verification of ETH Anomaly (Long-only, Profit Concentration, Data Gaps)

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

def check_data_gaps(candles):
    gaps = 0
    expected_diff = 4 * 3600 * 1000 # 4 hours in ms
    for i in range(1, len(candles)):
        diff = candles[i]['t'] - candles[i-1]['t']
        if diff > expected_diff + 60000: # allow 1 min tolerance
            gaps += 1
    return gaps

def run_verification(symbol, candles, atr):
    cash = CAPITAL_PER_ASSET
    position = None
    trade_pnls = []
    total_trades = 0

    for i in range(DONCHIAN_PERIOD + VOL_LOOKBACK, len(candles)):
        c = candles[i]
        
        if position is None:
            upper_band = max(x['h'] for x in candles[i-DONCHIAN_PERIOD:i])
            avg_vol = sum(x['v'] for x in candles[i-VOL_LOOKBACK:i]) / VOL_LOOKBACK
            
            # Verify: Only Long logic (No Short)
            if c['c'] > upper_band and c['v'] > avg_vol * 1.5:
                if atr[i] > 0:
                    sl_dist = ATR_MULT * atr[i]
                    sl_price = c['c'] - sl_dist
                    
                    equity = cash 
                    risk_amount = equity * RISK_PER_TRADE
                    qty = risk_amount / sl_dist
                    
                    cost = qty * c['c']
                    fee = cost * TOTAL_FEE
                    
                    if cost + fee > cash:
                        qty = cash / (c['c'] * (1 + TOTAL_FEE))
                        cost = qty * c['c']
                        fee = cost * TOTAL_FEE
                        
                    cash -= (cost + fee)
                    position = {"entry": c['c'], "sl": sl_price, "qty": qty}
                    total_trades += 1
        else:
            if c['l'] <= position['sl']:
                gross = position['qty'] * position['sl']
                exit_fee = gross * TOTAL_FEE
                cash += (gross - exit_fee)
                
                pnl_pct = ((position['sl'] - position['entry']) / position['entry']) * 100
                trade_pnls.append(pnl_pct)
                position = None
            else:
                new_sl = c['c'] - (ATR_MULT * atr[i])
                if new_sl > position['sl']:
                    position['sl'] = new_sl

    return trade_pnls, total_trades

def main():
    print("=== Verification of Donchian Anomaly ===\n")
    
    for symbol in SYMBOLS:
        print(f"--- {symbol} ---")
        candles = fetch_klines(symbol, INTERVAL, FETCH_DAYS)
        if len(candles) < DONCHIAN_PERIOD: continue
        
        # Check 1: Data Gaps
        gaps = check_data_gaps(candles)
        print(f"1. Data Quality: {len(candles)} candles | Gaps: {gaps} (Expected: 0)")
        
        # Check 2: Strategy Logic (Long-Only)
        print(f"2. Strategy Logic: Long-Only (Buy on Breakout). No Short Logic.")
        
        # Check 3: Trade Distribution
        atr = calc_atr(candles, 14)
        pnls, total = run_verification(symbol, candles, atr)
        
        if not pnls:
            print("3. No trades executed.")
            continue
            
        # Calculate stats
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        total_gross_profit = sum(wins)
        total_gross_loss = abs(sum(losses))
        net_pnl = total_gross_profit - total_gross_loss
        
        # Sort by highest profit
        sorted_wins = sorted(wins, reverse=True)
        top_5_sum = sum(sorted_wins[:5]) if len(sorted_wins) >= 5 else sum(sorted_wins)
        
        concentration = (top_5_sum / total_gross_profit * 100) if total_gross_profit > 0 else 0
        
        print(f"3. Trade Distribution:")
        print(f"   Total Trades: {total}")
        print(f"   Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"   Net PnL: {net_pnl:.2f}%")
        print(f"   Top 5 Wins: {top_5_sum:.2f}%")
        print(f"   Top 5 Concentration: {concentration:.1f}% of Gross Profit")
        
        if concentration > 50:
            print("   ⚠️ WARNING: Profits are heavily concentrated in top 5 trades (possible luck).")
        else:
            print("   ✅ OK: Profits are distributed across many trades.")
            
        print()

if __name__ == "__main__":
    main()
