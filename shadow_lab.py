#!/usr/bin/env python3
"""
shadow_lab.py — Parallel Hypothesis Testing (Shadow Only)
Runs every 1 hour. Tests both ENTRY and EXIT hypotheses in parallel.
No position limits: Infinite capital to eliminate Opportunity Cost.
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
DOLLAR_HISTORY_FILE = "dollar_history.json"
IRAN_NEWS_FILE = "iran_news_data.json"

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

def get_dollar_6h_change():
    try:
        data, _ = load_from_github(DOLLAR_HISTORY_FILE)
        if not data or len(data) < 2: return 0.0
        # data is list of [time_str, price]
        current = data[-1][1]
        # Find price ~6 hours ago
        cutoff = datetime.now(timezone.utc) - timezone.timedelta(hours=6)
        past = [p for t, p in data if datetime.fromisoformat(t.replace("Z", "+00:00")) <= cutoff]
        if past:
            oldest = past[0]
            return ((current - oldest) / oldest) * 100
        return 0.0
    except: return 0.0

def get_iran_sentiment():
    data, _ = load_from_github(IRAN_NEWS_FILE)
    if not data: return "unclear"
    stats = data.get("stats", {}) if isinstance(data, dict) else {}
    if stats and "by_btc_impact" in stats:
        up, down = stats["by_btc_impact"].get("up", 0), stats["by_btc_impact"].get("down", 0)
        if up > down * 2 and up >= 3: return "bullish"
        if down > up * 2 and down >= 3: return "bearish"
    return "neutral"

def main():
    print("=== SHADOW LAB (Multi-Hypothesis) ===")
    current_price = get_current_price()
    if not current_price: 
        print("Cannot get price.")
        return
    
    rsi = get_current_rsi()
    usd_chg = get_dollar_6h_change()
    iran_sent = get_iran_sentiment()
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

        # --- EXIT STRATEGIES ---
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
                trail_sl = max(trail_sl, entry * 1.006)
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
                    trail_pnl = ((current_price - entry) / entry * 100) - 0.6
                    t["pnl_pct"] = ((tp_pct - 0.6) + trail_pnl) / 2
                    updated_log.append(t)
                    print(f"Closed {strat} (Hybrid): {t['pnl_pct']:.2f}%")
                    continue
            updated_log.append(t)
            
        # --- NEW ENTRY STRATEGIES (Using Fixed TP for simplicity) ---
        elif strat in ["H1_IranSafeDip", "H2_USD_Momentum", "H3_ExtremeDip"]:
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

    # --- 2. Check for New Entries ---
    open_counts = {}
    for t in updated_log:
        if t.get("status") == "open":
            open_counts[t["strategy"]] = open_counts.get(t["strategy"], 0) + 1

    def open_trade(strategy_name, reason=""):
        if open_counts.get(strategy_name, 0) == 0: # Only 1 active per hypothesis
            new_trade = {
                "strategy": strategy_name,
                "status": "open",
                "entry": current_price,
                "sl": current_price * 0.98,
                "tp": current_price * 1.04,
                "entry_time": timestamp,
                "max_price": current_price,
                "trailing_active": False,
                "partial_closed": False,
                "reason": reason
            }
            updated_log.append(new_trade)
            print(f"Opened {strategy_name} @ {current_price:,.0f} | {reason}")

    # Hypothesis 1: DIP + Iran Safe (RSI < 30 AND Iran != Bearish)
    if rsi < 30 and iran_sent != "bearish":
        open_trade("H1_IranSafeDip", f"RSI={rsi:.1f}, Iran={iran_sent}")

    # Hypothesis 2: USD Momentum (USDT 6h change > 1.0%)
    if usd_chg > 1.0:
        open_trade("H2_USD_Momentum", f"USD 6h Chg={usd_chg:.2f}%")

    # Hypothesis 3: Extreme Dip (RSI < 25)
    if rsi < 25:
        open_trade("H3_ExtremeDip", f"RSI={rsi:.1f}")

    # --- 3. Existing DIP Strategies (A, F, G) ---
    if rsi < 30:
        open_trade("A_FixedTP", f"RSI={rsi:.1f}")
        open_trade("F_WideTrail", f"RSI={rsi:.1f}")
        open_trade("G_Hybrid", f"RSI={rsi:.1f}")

    if not any(t.get("status") == "open" for t in updated_log) and not any(k in ["H1_IranSafeDip", "H2_USD_Momentum", "H3_ExtremeDip"] for k in open_counts):
        print(f"No signals. RSI={rsi:.1f} | USD={usd_chg:.2f}% | Iran={iran_sent}")

    # Keep last 500 entries
    updated_log = updated_log[-500:]
    save_to_github(LAB_FILE, updated_log, lab_sha)
    print("Shadow Lab Updated.")

if __name__ == "__main__":
    main()
