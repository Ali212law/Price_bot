#!/usr/bin/env python3
"""
backtest_m6_multi_asset.py — 90-day Backtest for Multi-Asset (ETH, SOL, XRP)
- Fetches 90 days of 15m data.
- Tests Fixed (2/4) vs ATR Multipliers (1.5x, 2.0x, 2.5x).
- Metrics: n, WR%, Net%, Profit Factor, Max DD%, Expectancy (Avg PnL%).
- Split: FULL90 (Biased) vs OOS45 (Main Metric).
"""
import requests
import time
from datetime import datetime, timezone

ASSETS = ["ETH", "SOL", "XRP"]
SL_PCT = 2.0
TP_PCT = 4.0
TOTAL_FEE = 0.6
INITIAL_CAPITAL = 1_000_000.0
POS_SIZE = 35000.0

def fetch_wallex_15m(symbol, days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    pair = f"{symbol}USDT"
    
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    candles.append({
                        "t": int(data['t'][i]),
                        "h": float(data['h'][i]),
                        "l": float(data['l'][i]),
                        "c": float(data['c'][i])
                    })
            else:
                if not candles and pair.endswith("USDT"):
                    pair = f"{symbol}TMN"
                    url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={current}&to={to_ts}"
                    r = requests.get(url, timeout=10)
                    data = r.json()
                    if data.get('s') == 'ok':
                        for i in range(len(data['t'])):
                            candles.append({
                                "t": int(data['t'][i]),
                                "h": float(data['h'][i]),
                                "l": float(data['l'][i]),
                                "c": float(data['c'][i])
                            })
        except Exception:
            pass
        current = to_ts
        time.sleep(0.3)
    
    candles.sort(key=lambda x: x['t'])
    return candles, pair

def precompute_rsi(closes, period=14):
    rsi_vals = [50.0] * len(closes)
    if len(closes) < period + 1: return rsi_vals
    gains, losses = 0, 0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i-1]
        if ch > 0: gains += ch
        else: losses += abs(ch)
    ag, al = gains/period, losses/period
    rsi_vals[period] = 100 - (100/(1+ag/al)) if al > 0 else 100
    for i in range(period + 1, len(closes)):
        ch = closes[i] - closes[i-1]
        gain = ch if ch > 0 else 0
        loss = abs(ch) if ch < 0 else 0
        ag = (ag * (period - 1) + gain) / period
        al = (al * (period - 1) + loss) / period
        rsi_vals[i] = 100 - (100/(1+ag/al)) if al > 0 else 100
    return rsi_vals

def precompute_atr(candles, period=14):
    atr_vals = [0.0] * len(candles)
    if len(candles) < period + 1: return atr_vals
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]['h'], candles[i]['l'], candles[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        if i >= period:
            atr_vals[i] = sum(trs[-period:]) / period
    return atr_vals

def run_strategy(candles, rsi_array, atr_array, start_idx, end_idx, mode="fixed", atr_mult=1.5):
    trades = []
    position = None
    equity = INITIAL_CAPITAL
    peak_equity = INITIAL_CAPITAL
    max_dd = 0.0
    
    for i in range(start_idx + 30, end_idx):
        price = candles[i]['c']
        
        if position is not None:
            exit_p, reason, pnl = None, None, None
            
            if candles[i]['l'] <= position['sl']:
                exit_p, reason, pnl = position['sl'], "Hard_SL", -position['sl_pct'] - TOTAL_FEE
            elif candles[i]['h'] >= position['tp']:
                exit_p, reason, pnl = position['tp'], "TP", position['tp_pct'] - TOTAL_FEE
                
            if exit_p is not None:
                equity += (pnl / 100) * POS_SIZE
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity * 100
                max_dd = max(max_dd, dd)
                
                position.update({"status": "closed", "exit_reason": reason, "pnl_pct": pnl})
                trades.append(position)
                position = None
            continue
            
        if rsi_array[i] >= 30: continue
        
        sl_p, tp_p = SL_PCT, TP_PCT
        if mode == "atr":
            # Limit SL to [1.0%, 6.0%] to prevent extreme values
            raw_sl = (atr_array[i] * atr_mult / price) * 100
            sl_p = max(1.0, min(6.0, raw_sl))
            tp_p = sl_p * 2
            
        position = {
            'entry': price, 'sl': price*(1-sl_p/100), 'tp': price*(1+tp_p/100),
            'sl_pct': sl_p, 'tp_pct': tp_p, 'status': 'open'
        }

    closed = [t for t in trades if t['status'] == 'closed']
    n = len(closed)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "eq": equity, "pf": 0, "dd": 0, "exp": 0}
    
    wins = sum(1 for t in closed if t['pnl_pct'] > 0)
    net = sum(t['pnl_pct'] for t in closed)
    
    gross_win = sum(t['pnl_pct'] for t in closed if t['pnl_pct'] > 0)
    gross_loss = abs(sum(t['pnl_pct'] for t in closed if t['pnl_pct'] < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    exp = net / n
    
    return {"n": n, "wr": wins/n*100, "net": net, "eq": equity, "pf": pf, "dd": max_dd, "exp": exp}

def main():
    for symbol in ASSETS:
        candles, pair = fetch_wallex_15m(symbol, 90)
        if not candles or len(candles) < 100:
            print(f"Skipping {symbol} (insufficient data)")
            continue
            
        closes = [c['c'] for c in candles]
        rsi = precompute_rsi(closes)
        atr = precompute_atr(candles)
        
        total_len = len(candles)
        mid_point = total_len // 2
        
        print(f"\n=== {symbol} ({pair}) | Total Candles: {total_len} ===")
        
        configs = [
            ("Fixed(2/4)", "fixed", 1.5),
            ("ATR(1.5x)", "atr", 1.5),
            ("ATR(2.0x)", "atr", 2.0),
            ("ATR(2.5x)", "atr", 2.5)
        ]
        
        print(f"{'Config':<12} | {'OOS45 (Out-of-Sample)':<60}")
        print(f"{'':<12} | {'n':>4} {'WR%':>6} {'Net%':>7} {'PF':>5} {'MaxDD%':>7} {'Exp%':>7} {'Eq':>10}")
        print("-" * 90)
        
        for name, mode, mult in configs:
            res_oos = run_strategy(candles, rsi, atr, mid_point, total_len, mode=mode, atr_mult=mult)
            print(f"{name:<12} | {res_oos['n']:>4} {res_oos['wr']:>6.1f} {res_oos['net']:>+7.1f} {res_oos['pf']:>5.2f} {res_oos['dd']:>7.1f} {res_oos['exp']:>+7.2f} {res_oos['eq']:>10,.0f}")

if __name__ == "__main__":
    main()
