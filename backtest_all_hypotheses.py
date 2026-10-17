#!/usr/bin/env python3
"""
backtest_all_hypotheses.py — Test 5 Hypotheses (H6, H8, H9, H10, H11)
- Unified engine, DIP only, High/Low triggers, SL priority.
- Split: FULL90 (biased) vs OOS45 (main metric).
- Baseline A is used as reference.
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
BTC_HISTORY_FILE = "btc_history.json"
PRICE_COMPONENTS_FILE = "price_components.json"

# Engine Params
SL_PCT = 2.0
TP_PCT = 4.0
RISK_TOMAN = 700.0
POS_SIZE = RISK_TOMAN / (SL_PCT / 100) # 35,000
TOTAL_FEE = 0.6
INITIAL_CAPITAL = 1_000_000.0
MAX_OPEN = 1

# Time split (approx 90 days = 8640 candles of 15m)
# But we fetch dynamically, so we'll just split the array in half.

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

def get_dollar_history():
    """Fetch dollar history from price_components.json"""
    data = gh_load(PRICE_COMPONENTS_FILE)
    if not data: return {}
    # Map timestamp (rounded to hour) -> usdt_tmn
    d_map = {}
    for row in data:
        try:
            t = datetime.fromisoformat(row["time"].replace("Z","+00:00")).replace(tzinfo=None)
            d_map[t] = row.get("usdt_tmn", 0)
        except: pass
    return d_map

def get_dollar_6h_chg(d_map, current_time):
    if not d_map: return None
    # Find closest past time up to 6h ago
    target = current_time - timedelta(hours=6)
    # Simple lookup: find max timestamp <= target
    past_times = [t for t in d_map.keys() if t <= target]
    if not past_times: return None
    past_t = max(past_times)
    curr_times = [t for t in d_map.keys() if t <= current_time]
    if not curr_times: return None
    curr_t = max(curr_times)
    
    past_p = d_map[past_t]
    curr_p = d_map[curr_t]
    if past_p > 0:
        return ((curr_p - past_p) / past_p) * 100
    return None

def run_hypothesis(name, candles, rsi_array, atr_array, d_map, start_idx, end_idx):
    trades = []
    position = None
    capital = INITIAL_CAPITAL
    
    for i in range(start_idx + 30, end_idx):
        price = candles[i]['c']
        dt = datetime.fromtimestamp(candles[i]['t'], tz=timezone.utc)
        
        chg24h = ((price - candles[i-96]['c']) / candles[i-96]['c']) * 100 if i >= 96 else 0
        usd_chg = get_dollar_6h_chg(d_map, dt.replace(tzinfo=None)) if d_map else None
        
        if position is not None:
            exit_p, reason, pnl = None, None, None
            
            # 1. Hard SL
            if candles[i]['l'] <= position['sl']:
                exit_p, reason, pnl = position['sl'], "Hard_SL", -position['sl_pct'] - TOTAL_FEE
                
            # 2. TP (if not H11)
            elif name != "H11_TIMEEXIT_48H" and candles[i]['h'] >= position['tp']:
                exit_p, reason, pnl = position['tp'], "TP", position['tp_pct'] - TOTAL_FEE
                
            # 3. Time Exit (H11)
            elif name == "H11_TIMEEXIT_48H":
                hours_held = (dt - position['entry_dt']).total_seconds() / 3600
                if hours_held >= 48:
                    exit_p, reason, pnl = price, "time_exit", (price - position['entry'])/position['entry']*100 - TOTAL_FEE
                    
            if exit_p is not None:
                capital += (pnl / 100) * POS_SIZE
                position.update({"status": "closed", "exit_price": exit_p, "exit_reason": reason, "pnl_pct": pnl})
                trades.append(position)
                position = None
            continue
            
        # Check Entry
        if rsi_array[i] >= 30: continue # Base DIP
        if name == "H9_RSI25_CHG" and not (rsi_array[i] < 25 and -2.0 <= chg24h <= -1.5): continue
        if name == "H10_SESSION" and 18 <= dt.hour < 24: continue
        if name == "H8_DOLLAR_FILTER" and (usd_chg is None or abs(usd_chg) >= 0.5): continue
        
        # Setup SL/TP
        sl_p, tp_p = SL_PCT, TP_PCT
        if name == "H6_ATR_STOP":
            sl_p = max(1.5, min(3.0, (atr_array[i] * 1.5 / price) * 100))
            tp_p = sl_p * 2
            
        position = {
            'entry': price, 'entry_dt': dt, 'sl': price*(1-sl_p/100), 'tp': price*(1+tp_p/100),
            'sl_pct': sl_p, 'tp_pct': tp_p, 'status': 'open'
        }

    return trades, capital

def get_stats(trades, capital, label):
    closed = [t for t in trades if t['status'] == 'closed']
    n = len(closed)
    if n == 0: return {"n": 0, "wr": 0, "net": 0, "avg": 0, "equity": capital}
    
    wins = sum(1 for t in closed if t['pnl_pct'] > 0)
    net = sum(t['pnl_pct'] for t in closed)
    avg = net / n
    
    by_regime = defaultdict(lambda: {"n":0, "w":0})
    for t in closed:
        reg = "bear" if t.get('chg24h', 0) < -1.5 else ("bull" if t.get('chg24h', 0) > 1.5 else ("range" if abs(t.get('chg24h', 0)) < 0.5 else "chop"))
        by_regime[reg]["n"] += 1
        if t['pnl_pct'] > 0: by_regime[reg]["w"] += 1
        
    return {"n": n, "wr": wins/n*100, "net": net, "avg": avg, "equity": capital, "regimes": dict(by_regime)}

def main():
    candles = fetch_wallex_15m(90)
    if not candles: return
    
    closes = [c['c'] for c in candles]
    print("Precomputing RSI & ATR...")
    rsi = precompute_rsi(closes)
    atr = precompute_atr(candles)
    
    print("Loading Dollar History...")
    d_map = get_dollar_history()
    
    total_len = len(candles)
    mid_point = total_len // 2 # 45 days
    
    hypotheses = ["H10_SESSION", "H11_TIMEEXIT_48H", "H6_ATR_STOP", "H9_RSI25_CHG", "H8_DOLLAR_FILTER"]
    
    results = {}
    
    # Run Baseline A for comparison
    print("Running Baseline A (Reference)...")
    trades_full, cap_full = run_hypothesis("BASE_A", candles, rsi, atr, d_map, 0, total_len)
    trades_oos, cap_oos = run_hypothesis("BASE_A", candles, rsi, atr, d_map, mid_point, total_len)
    results["BASE_A"] = {"full": get_stats(trades_full, cap_full, "Full"), "oos": get_stats(trades_oos, cap_oos, "OOS")}

    for h in hypotheses:
        print(f"Running {h}...")
        trades_full, cap_full = run_hypothesis(h, candles, rsi, atr, d_map, 0, total_len)
        trades_oos, cap_oos = run_hypothesis(h, candles, rsi, atr, d_map, mid_point, total_len)
        results[h] = {"full": get_stats(trades_full, cap_full, "Full"), "oos": get_stats(trades_oos, cap_oos, "OOS")}

    # Print Summary
    print("\n" + "="*80)
    print(f"{'Strategy':<18} | {'FULL90 (Biased)':<30} | {'OOS45 (Main Metric)':<30}")
    print(f"{'':<18} | {'n':>4} {'WR%':>6} {'Net%':>7} {'Eq':>10} | {'n':>4} {'WR%':>6} {'Net%':>7} {'Eq':>10}")
    print("-" * 80)
    
    for name in ["BASE_A"] + hypotheses:
        f = results[name]["full"]
        o = results[name]["oos"]
        print(f"{name:<18} | {f['n']:>4} {f['wr']:>6.1f} {f['net']:>+7.1f} {f['equity']:>10,.0f} | {o['n']:>4} {o['wr']:>6.1f} {o['net']:>+7.1f} {o['equity']:>10,.0f}")
        
    print("\n--- Detailed OOS Breakdown ---")
    for name in hypotheses:
        o = results[name]["oos"]
        if o['n'] > 0:
            print(f"{name}: Regimes = {o.get('regimes')}")
        else:
            print(f"{name}: No trades in OOS.")

if __name__ == "__main__":
    main()
