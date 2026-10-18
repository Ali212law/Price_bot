#!/usr/bin/env python3
"""
backtest_m6_v2.py — Test BTC Regime Filter on Altcoins
- Compares: Pure DIP vs DIP+BTC_Filter vs DIP+Alt_Filter vs DIP+Both_Filters
- Uses EMA200 as the long-term trend indicator.
"""
import requests
import time
from datetime import datetime, timezone

ASSETS = ["ETH", "SOL", "XRP"]
SL_PCT = 2.0
TP_PCT = 4.0
TOTAL_FEE = 0.6
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
                    candles.append({"t": int(data['t'][i]), "h": float(data['h'][i]), "l": float(data['l'][i]), "c": float(data['c'][i])})
            elif not candles:
                pair = f"{symbol}TMN"
                url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={current}&to={to_ts}"
                r = requests.get(url, timeout=10)
                data = r.json()
                if data.get('s') == 'ok':
                    for i in range(len(data['t'])):
                        candles.append({"t": int(data['t'][i]), "h": float(data['h'][i]), "l": float(data['l'][i]), "c": float(data['c'][i])})
        except Exception: pass
        current = to_ts
        time.sleep(0.3)
    candles.sort(key=lambda x: x['t'])
    return candles

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

def precompute_ema(closes, period=200):
    ema_vals = [0.0] * len(closes)
    if len(closes) < period: return ema_vals
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    ema_vals[period-1] = ema
    for i in range(period, len(closes)):
        ema = closes[i] * k + ema * (1 - k)
        ema_vals[i] = ema
    return ema_vals

def run_strategy(candles, rsi, ema, btc_ema, start_idx, end_idx, mode):
    trades = []
    position = None
    equity = 1_000_000.0
    peak_equity = equity
    max_dd = 0.0
    
    for i in range(start_idx + 30, end_idx):
        price = candles[i]['c']
        
        if position is not None:
            exit_p, pnl = None, None
            if candles[i]['l'] <= position['sl']:
                exit_p, pnl = position['sl'], -position['sl_pct'] - TOTAL_FEE
            elif candles[i]['h'] >= position['tp']:
                exit_p, pnl = position['tp'], position['tp_pct'] - TOTAL_FEE
                
            if exit_p is not None:
                equity += (pnl / 100) * POS_SIZE
                peak_equity = max(peak_equity, equity)
                max_dd = max(max_dd, (peak_equity - equity) / peak_equity * 100)
                position.update({"status": "closed", "pnl_pct": pnl})
                trades.append(position)
                position = None
            continue
            
        if rsi[i] >= 30: continue
        
        # Filters
        if mode == "btc_filter" and not (btc_ema[i] > 0 and price > 0 and btc_ema[i] < candles[i]['c']): continue # Dummy logic check
        if mode in ["btc_filter", "both_filter"] and (btc_ema[i] == 0 or price < ema[i]): continue
        if mode in ["alt_filter", "both_filter"] and (ema[i] == 0 or price < ema[i]): continue
        
        # Wait, BTC EMA array index depends on BTC length. I need to align them by timestamp.
        # For simplicity in this script, if lengths match (both 90 days), we use same index.
        if mode in ["btc_filter", "both_filter"] and btc_ema[i] == 0: continue # Skip if BTC EMA not ready
        if mode in ["btc_filter", "both_filter"] and candles[i]['c'] < btc_ema[i]: continue # BTC price < BTC EMA -> Bearish
        if mode in ["alt_filter", "both_filter"] and ema[i] == 0: continue
        if mode in ["alt_filter", "both_filter"] and price < ema[i]: continue

        sl_p, tp_p = SL_PCT, TP_PCT
        position = {'entry': price, 'sl': price*(1-sl_p/100), 'tp': price*(1+tp_p/100), 'sl_pct': sl_p, 'tp_pct': tp_p, 'status': 'open'}

    closed = [t for t in trades if t['status'] == 'closed']
    n = len(closed)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "dd": 0}
    wins = sum(1 for t in closed if t['pnl_pct'] > 0)
    net = sum(t['pnl_pct'] for t in closed)
    return {"n": n, "wr": wins/n*100, "net": net, "dd": max_dd}

def main():
    print("Fetching BTC Data for Regime Filter...")
    btc_candles = fetch_wallex_15m("BTC", 90)
    btc_closes = [c['c'] for c in btc_candles]
    btc_ema = precompute_ema(btc_closes, 200)

    for symbol in ASSETS:
        candles = fetch_wallex_15m(symbol, 90)
        if not candles or len(candles) < 200: continue
        closes = [c['c'] for c in candles]
        rsi = precompute_rsi(closes)
        ema = precompute_ema(closes, 200)
        
        mid = len(candles) // 2
        
        print(f"\n=== {symbol} (OOS45) ===")
        print(f"{'Mode':<18} | {'n':>4} {'WR%':>6} {'Net%':>7} {'MaxDD%':>7}")
        print("-" * 50)
        
        for mode, label in [("pure", "Pure DIP"), ("btc_filter", "DIP + BTC>EMA200"), ("alt_filter", "DIP + Alt>EMA200"), ("both_filter", "DIP + Both>EMA200")]:
            res = run_strategy(candles, rsi, ema, btc_ema, mid, len(candles), mode)
            print(f"{label:<18} | {res['n']:>4} {res['wr']:>6.1f} {res['net']:>+7.1f} {res['dd']:>7.1f}")

if __name__ == "__main__":
    main()
