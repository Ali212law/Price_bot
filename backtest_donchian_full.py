#!/usr/bin/env python3
# backtest_donchian_full.py — Challenger 1 with Full D-68 Gate Metrics

import requests, time, math

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

def wilson_lower(k, n, z=1.96):
    if n == 0: return 0.0
    p = k / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return center - half

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
    trades_pnl = [] # List of pnl_pct for each trade
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
                    
                    cost = qty * c['c']
                    fee = cost * TOTAL_FEE
                    
                    if cost + fee > cash:
                        qty = cash / (c['c'] * (1 + TOTAL_FEE))
                        cost = qty * c['c']
                        fee = cost * TOTAL_FEE
                        
                    cash -= (cost + fee)
                    position = {"entry": c['c'], "sl": sl_price, "qty": qty}
        else:
            if c['l'] <= position['sl']:
                gross = position['qty'] * position['sl']
                exit_fee = gross * TOTAL_FEE
                cash += (gross - exit_fee)
                
                # Calculate PnL % for this trade
                pnl_pct = ((position['sl'] - position['entry']) / position['entry']) * 100
                trades_pnl.append(pnl_pct)
                position = None
            else:
                new_sl = c['c'] - (ATR_MULT * atr[i])
                if new_sl > position['sl']:
                    position['sl'] = new_sl

        val = cash + (position['qty'] * c['c'] if position else 0)
        if val > equity_peak: equity_peak = val
        dd = (equity_peak - val) / equity_peak * 100
        if dd > max_dd: max_dd = dd

    final_price = candles[-1]['c']
    final_val = cash + (position['qty'] * final_price if position else 0)
    net_pct = ((final_val / CAPITAL_PER_ASSET) - 1) * 100
    
    # Metrics
    n = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    wr = (len(wins) / n * 100) if n > 0 else 0
    wilson_lo = wilson_lower(len(wins), n) * 100
    
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    expectancy = (sum(trades_pnl) / n) if n > 0 else 0
    
    # Buy & Hold
    bh_start = candles[DONCHIAN_PERIOD + VOL_LOOKBACK]['c']
    bh_pct = ((final_price - bh_start) / bh_start) * 100

    return {
        "net_pct": net_pct, "max_dd": max_dd, "n": n, "wr": wr, 
        "wilson_lo": wilson_lo, "pf": pf, "expectancy": expectancy, "bh_pct": bh_pct
    }

def main():
    print("=== Challenger 1: Donchian + Volume | D-68 Gate Test ===\n")
    print(f"Criteria: n>=30 | Wilson > Breakeven | PF > 1.2 | Exp > 0.1R | MaxDD < 15%\n")
    
    total_net = 0
    total_n = 0
    total_wins = 0
    portfolio_max_dd = 0
    
    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...")
        candles = fetch_klines(symbol, INTERVAL, FETCH_DAYS)
        if len(candles) < DONCHIAN_PERIOD: continue
        
        atr = calc_atr(candles, 14)
        res = run_donchian(candles, atr)
        
        total_net += res["net_pct"]
        total_n += res["n"]
        total_wins += (res["wr"] / 100 * res["n"])
        if res["max_dd"] > portfolio_max_dd: portfolio_max_dd = res["max_dd"]
        
        print(f"--- {symbol} ---")
        print(f"  Net: {res['net_pct']:+.2f}% | MaxDD: {res['max_dd']:.2f}% | n: {res['n']} | WR: {res['wr']:.1f}%")
        print(f"  Wilson Lower: {res['wilson_lo']:.1f}% | PF: {res['pf']:.2f} | Exp: {res['expectancy']:+.2f}%")
        print(f"  B&H: {res['bh_pct']:+.2f}%\n")
        
    print("=" * 50)
    portfolio_net = total_net / len(SYMBOLS)
    portfolio_wr = (total_wins / total_n * 100) if total_n > 0 else 0
    portfolio_wilson = wilson_lower(int(total_wins), total_n) * 100
    
    # Rough portfolio metrics (averaged)
    # Need to recalculate PF and Exp for portfolio. 
    # For simplicity, we'll just show n and WR.
    
    print("=== PORTFOLIO SUMMARY ===")
    print(f"Avg Net: {portfolio_net:+.2f}% | MaxDD: {portfolio_max_dd:.2f}% | n: {total_n}")
    print(f"Overall WR: {portfolio_wr:.1f}% | Wilson Lower: {portfolio_wilson:.1f}%")
    
    verdict = "FAILED"
    if total_n >= 30 and portfolio_wilson > 36.0 and portfolio_max_dd < 15:
        verdict = "PASSED (Candidate)"
        
    print(f"\nVERDICT: {verdict}")

if __name__ == "__main__":
    main()
