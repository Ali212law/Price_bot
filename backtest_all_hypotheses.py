#!/usr/bin/env python3
"""
backtest_all_hypotheses.py — Test 4 Hypotheses (H8, H9, H10, H11)
- Unified engine, DIP only, High/Low triggers, SL priority.
- Split: FULL90 (biased) vs OOS45 (main metric).
- Baseline A is used as reference.
- UPDATED: Sum_net breakdown (SL/TP/TimeExit), H8 Near-Miss logger, H6 Archived.
"""
import requests
import time
import json
import base64
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = "Ali212law/Price_bot"
PRICE_COMPONENTS_FILE = "price_components.json"

# Engine Params
SL_PCT = 2.0
TP_PCT = 4.0
RISK_TOMAN = 700.0
POS_SIZE = RISK_TOMAN / (SL_PCT / 100) # 35,000
TOTAL_FEE = 0.6
INITIAL_CAPITAL = 1_000_000.0
MAX_OPEN = 1

def gh_load(fn):
    try:
        r = requests.get(f"https://api.github.com/repos/{GH_REPO}/contents/{fn}",
                         headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return json.loads(base64.b64decode(d["content"]).decode())
    except: pass
    return None

def fetch_wallex_15m(days=90):
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    print(f"Fetching {days} days of 15m data...")
    current = start
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol=BTCTMN&resolution=15&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    c = float(data['c'][i])
                    if c > 100_000_000_000: c /= 10
                    candles.append({
                        "t": int(data['t'][i]),
                        "h": float(data['h'][i])/(10 if float(data['h'][i])>100_000_000_000 else 1),
                        "l": float(data['l'][i])/(10 if float(data['l'][i])>100_000_000_000 else 1),
                        "c": c
                    })
        except: pass
        current = to_ts
        time.sleep(0.3)
    candles.sort(key=lambda x: x['t'])
    print(f"Total candles: {len(candles)}")
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

def get_dollar_history():
    data = gh_load(PRICE_COMPONENTS_FILE)
    if not data: return {}
    d_map = {}
    for row in data:
        try:
            t = datetime.fromisoformat(row["time"].replace("Z","+00:00")).replace(tzinfo=None)
            d_map[t] = row.get("usdt_tmn", 0)
        except: pass
    return d_map

def get_dollar_6h_chg(d_map, current_time):
    if not d_map: return None
    target = current_time - timedelta(hours=6)
    past_times = [t for t in d_map.keys() if t <= target]
    if not past_times: return None
    past_t = max(past_times)
    curr_times = [t for t in d_map.keys() if t <= current_time]
    if not curr_times: return None
    curr_t = max(curr_times)
    past_p = d_map[past_t]
    curr_p = d_map[curr_t]
    if past_p > 0: return ((curr_p - past_p) / past_p) * 100
    return None

def run_hypothesis(name, candles, rsi_array, d_map, start_idx, end_idx):
    trades = []
    position = None
    capital = INITIAL_CAPITAL
    
    sum_sl, sum_tp, sum_time = 0.0, 0.0, 0.0
    h8_near_miss = 0
    
    for i in range(start_idx + 30, end_idx):
        price = candles[i]['c']
        dt = datetime.fromtimestamp(candles[i]['t'], tz=timezone.utc)
        chg24h = ((price - candles[i-96]['c']) / candles[i-96]['c']) * 100 if i >= 96 else 0
        usd_chg = get_dollar_6h_chg(d_map, dt.replace(tzinfo=None)) if d_map else None
        
        if position is not None:
            exit_p, reason, pnl = None, None, None
            
            if candles[i]['l'] <= position['sl']:
                exit_p, reason, pnl = position['sl'], "Hard_SL", -position['sl_pct'] - TOTAL_FEE
                sum_sl += pnl
                
            elif name != "H11_TIMEEXIT_48H" and candles[i]['h'] >= position['tp']:
                exit_p, reason, pnl = position['tp'], "TP", position['tp_pct'] - TOTAL_FEE
                sum_tp += pnl
                
            elif name == "H11_TIMEEXIT_48H":
                hours_held = (dt - position['entry_dt']).total_seconds() / 3600
                if hours_held >= 48:
                    exit_p, reason, pnl = price, "time_exit", (price - position['entry'])/position['entry']*100 - TOTAL_FEE
                    sum_time += pnl
                    
            if exit_p is not None:
                capital += (pnl / 100) * POS_SIZE
                position.update({"status": "closed", "exit_price": exit_p, "exit_reason": reason, "pnl_pct": pnl})
                trades.append(position)
                position = None
            continue
            
        if rsi_array[i] >= 30: continue
        
        if name == "H9_RSI25_CHG" and not (rsi_array[i] < 25 and -2.0 <= chg24h <= -1.5): continue
        if name == "H10_SESSION" and 18 <= dt.hour < 24: continue
        if name == "H8_DOLLAR_FILTER":
            if usd_chg is None or abs(usd_chg) >= 0.5:
                h8_near_miss += 1
                continue
        
        sl_p, tp_p = SL_PCT, TP_PCT
        position = {
            'entry': price, 'entry_dt': dt, 'sl': price*(1-sl_p/100), 'tp': price*(1+tp_p/100),
            'sl_pct': sl_p, 'tp_pct': tp_p, 'status': 'open'
        }

    return trades, capital, {"sl": sum_sl, "tp": sum_tp, "time": sum_time, "miss": h8_near_miss}

def get_stats(trades, capital, breakdown):
    closed = [t for t in trades if t['status'] == 'closed']
    n = len(closed)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "equity": capital, "breakdown": breakdown}
    
    wins = sum(1 for t in closed if t['pnl_pct'] > 0)
    net = sum(t['pnl_pct'] for t in closed)
    return {"n": n, "wr": wins/n*100, "net": net, "equity": capital, "breakdown": breakdown}

def main():
    candles = fetch_wallex_15m(90)
    if not candles: return
    
    closes = [c['c'] for c in candles]
    print("Precomputing RSI...")
    rsi = precompute_rsi(closes)
    print("Loading Dollar History...")
    d_map = get_dollar_history()
    
    total_len = len(candles)
    mid_point = total_len // 2
    
    hypotheses = ["H10_SESSION", "H11_TIMEEXIT_48H", "H9_RSI25_CHG", "H8_DOLLAR_FILTER"]
    results = {}
    
    print("Running Baseline A...")
    t_full, c_full, b_full = run_hypothesis("BASE_A", candles, rsi, d_map, 0, total_len)
    t_oos, c_oos, b_oos = run_hypothesis("BASE_A", candles, rsi, d_map, mid_point, total_len)
    results["BASE_A"] = {"full": get_stats(t_full, c_full, b_full), "oos": get_stats(t_oos, c_oos, b_oos)}

    for h in hypotheses:
        print(f"Running {h}...")
        t_full, c_full, b_full = run_hypothesis(h, candles, rsi, d_map, 0, total_len)
        t_oos, c_oos, b_oos = run_hypothesis(h, candles, rsi, d_map, mid_point, total_len)
        results[h] = {"full": get_stats(t_full, c_full, b_full), "oos": get_stats(t_oos, c_oos, b_oos)}

    print("\n" + "="*90)
    print(f"{'Strategy':<18} | {'FULL90 (Biased)':<30} | {'OOS45 (Main Metric)':<30}")
    print(f"{'':<18} | {'n':>4} {'WR%':>6} {'Net%':>7} {'Eq':>10} | {'n':>4} {'WR%':>6} {'Net%':>7} {'Eq':>10}")
    print("-" * 90)
    
    for name in ["BASE_A"] + hypotheses:
        f, o = results[name]["full"], results[name]["oos"]
        print(f"{name:<18} | {f['n']:>4} {f['wr']:>6.1f} {f['net']:>+7.1f} {f['equity']:>10,.0f} | {o['n']:>4} {o['wr']:>6.1f} {o['net']:>+7.1f} {o['equity']:>10,.0f}")
        
    print("\n--- OOS45 Detailed Breakdown (SL / TP / Time / Miss) ---")
    for name in ["BASE_A"] + hypotheses:
        o = results[name]["oos"]
        b = o["breakdown"]
        print(f"{name:<18} | SL: {b['sl']:>+6.1f}% | TP: {b['tp']:>+6.1f}% | Time: {b['time']:>+6.1f}% | H8_Miss: {b['miss']}")

if __name__ == "__main__":
    main()
