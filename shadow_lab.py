#!/usr/bin/env python3
"""
shadow_lab.py — Parallel Hypothesis Testing (Shadow Only)
Runs every 1 hour. Tests 3 different exit strategies for DIP signals in parallel.
No position limits: Simulates infinite capital to eliminate Opportunity Cost.
"""
import requests
import json
import os
import base64
import time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = "Ali212law/Price_bot"
LAB_FILE = "shadow_lab_trades.json"
BTC_HISTORY_FILE = "btc_history.json"

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return None, None
    except: return None, None

def save_to_github(filename, data, sha=None):
    try:
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def get_current_price():
    try:
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=10)
        symbols = r.json().get("result", {}).get("symbols", {})
        btc_tmn = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        if btc_tmn > 100_000_000_000: btc_tmn /= 10
        return btc_tmn
    except: return None

def get_current_rsi():
    try:
        data, _ = load_from_github(BTC_HISTORY_FILE)
        if not data or len(data) < 20: return 50.0
        closes = [p for t, p in data[-20:]]
        gains, losses = [], []
        for i in range(1, len(closes)):
            ch = closes[i] - closes[i-1]
            if ch > 0: gains.append(ch); losses.append(0)
            else: gains.append(0); losses.append(abs(ch))
        ag = sum(gains[-14:]) / 14
        al = sum(losses[-14:]) / 14
        return 100 - (100 / (1 + (ag/al))) if al > 0 else 100
    except: return 50.0

def main():
    print("=== SHADOW LAB (Multi-Strategy Exit) ===")
    current_price = get_current_price()
    if not current_price: 
        print("Cannot get price.")
        return
    
    rsi = get_current_rsi()
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()
    
    lab_log, lab_sha = load_from_github(LAB_FILE)
    if not lab_log: lab_log = []
    
    # --- 1. Update Active Positions ---
    updated_log = []
    for t in lab_log:
        if t.get("status") != "open":
            updated_log.append(t)
            continue
            
        strat = t["strategy"]
        entry = t["entry"]
        sl_pct, tp_pct = 2.0, 4.0
        
        # Check Hard SL for all strategies
        if current_price <= entry * (1 - sl_pct/100):
            t["status"] = "closed"
            t["exit_price"] = current_price
            t["exit_reason"] = "Hard_SL"
            t["exit_time"] = timestamp
            t["pnl_pct"] = -sl_pct - 0.6
            updated_log.append(t)
            print(f"Closed {strat} (Hard SL): {t['pnl_pct']:.2f}%")
            continue

        # Strategy A: Fixed TP 4%
        if strat == "A_FixedTP":
            if current_price >= entry * (1 + tp_pct/100):
                t["status"] = "closed"
                t["exit_price"] = current_price
                t["exit_reason"] = "Fixed_TP"
                t["exit_time"] = timestamp
                t["pnl_pct"] = tp_pct - 0.6
                updated_log.append(t)
                print(f"Closed {strat} (TP): {t['pnl_pct']:.2f}%")
            else:
                updated_log.append(t)

        # Strategy F: Wide Trailing Stop (Act +4%, Trail 5%)
        elif strat == "F_WideTrail":
            t["max_price"] = max(t.get("max_price", entry), current_price)
            if current_price >= entry * 1.04:
                t["trailing_active"] = True
                
            if t.get("trailing_active"):
                trail_sl = t["max_price"] * 0.95
                trail_sl = max(trail_sl, entry * 1.006) # Breakeven + cost
                if current_price <= trail_sl:
                    t["status"] = "closed"
                    t["exit_price"] = current_price
                    t["exit_reason"] = "Trail_SL"
                    t["exit_time"] = timestamp
                    t["pnl_pct"] = ((current_price - entry) / entry * 100) - 0.6
                    updated_log.append(t)
                    print(f"Closed {strat} (Trail): {t['pnl_pct']:.2f}%")
                    continue
            updated_log.append(t)

        # Strategy G: Hybrid (50% at 4%, 50% Trail 5%)
        elif strat == "G_Hybrid":
            t["max_price"] = max(t.get("max_price", entry), current_price)
            if not t.get("partial_closed") and current_price >= entry * 1.04:
                t["partial_closed"] = True
                
            if t.get("partial_closed"):
                trail_sl = t["max_price"] * 0.95
                trail_sl = max(trail_sl, entry * 1.006)
                if current_price <= trail_sl:
                    t["status"] = "closed"
                    t["exit_price"] = current_price
                    t["exit_reason"] = "Hybrid_Trail"
                    t["exit_time"] = timestamp
                    # PnL is average of 50% at 4% and 50% at trail
                    trail_pnl = ((current_price - entry) / entry * 100) - 0.6
                    t["pnl_pct"] = ((tp_pct - 0.6) + trail_pnl) / 2
                    updated_log.append(t)
                    print(f"Closed {strat} (Hybrid): {t['pnl_pct']:.2f}%")
                    continue
            updated_log.append(t)

    # --- 2. Check for New DIP Signal ---
    # Count open positions for each strategy
    open_counts = {"A_FixedTP": 0, "F_WideTrail": 0, "G_Hybrid": 0}
    for t in updated_log:
        if t.get("status") == "open":
            open_counts[t["strategy"]] += 1

    if rsi < 30:
        print(f"DIP Signal Detected! RSI={rsi:.1f}")
        # Open new positions in parallel for all 3 strategies
        for strat in ["A_FixedTP", "F_WideTrail", "G_Hybrid"]:
            # Since it's a shadow lab with infinite capacity, we just open a new one if none is active for that strategy (or we can allow multiple, but let's stick to 1 per strategy to keep it clean)
            if open_counts[strat] == 0:
                new_trade = {
                    "strategy": strat,
                    "status": "open",
                    "entry": current_price,
                    "sl": current_price * 0.98,
                    "tp": current_price * 1.04,
                    "entry_time": timestamp,
                    "max_price": current_price,
                    "trailing_active": False,
                    "partial_closed": False
                }
                updated_log.append(new_trade)
                print(f"Opened {strat} @ {current_price:,.0f}")
    else:
        print(f"No DIP signal. RSI={rsi:.1f}")

    # Keep last 500 entries
    updated_log = updated_log[-500:]
    save_to_github(LAB_FILE, updated_log, lab_sha)
    print("Shadow Lab Updated.")

if __name__ == "__main__":
    main()
