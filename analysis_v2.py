#!/usr/bin/env python3
"""
analysis_v2.py — Fix TOP duplicate counts & correct priority-suppressed logic
"""
import json
from collections import Counter, defaultdict

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
CODE_VERSIONS = ("paper_trade33", "paper_trade34")

def load(fn):
    try:
        with open(fn) as f: return json.load(f)
    except: return []

def main():
    print("=" * 60)
    print("ANALYSIS V2 — Dedupe & Priority Fix")
    print("=" * 60)
    
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    all_trades = [t for t in p + s if (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]

    # --- A: Fix TOP double counting ---
    print("\n[1] TOP Deduplication (Original vs Unique)")
    tops = [t for t in all_trades if t.get("signal_type") == "TOP"]
    
    seen = set()
    unique_tops = []
    for t in tops:
        key = (t.get("entry_time"), t.get("entry_price"), t.get("side"))
        if key not in seen:
            seen.add(key)
            unique_tops.append(t)
            
    print(f"  Original TOP count: {len(tops)}")
    print(f"  Unique TOP count:   {len(unique_tops)}")
    
    # Recalculate TOP stats
    closed_tops = [t for t in unique_tops if t.get("status") == "closed"]
    pnls = [(t.get("profit_net_toman") or 0) for t in closed_tops]
    if pnls:
        wins = sum(1 for x in pnls if x > 0)
        print(f"  TOP Closed (Unique): {len(pnls)}")
        print(f"  TOP WR (Unique):     {wins/len(pnls)*100:.1f}%")
        print(f"  TOP Net (Unique):    {sum(pnls):+.0f}")

    # --- B: Fix Priority Suppressed logic ---
    print("\n[2] Priority Suppressed (Corrected Logic)")
    # We need to check every trade's metadata to see what *could* have fired
    suppressed_counts = Counter()
    
    for t in all_trades:
        m = t.get("metadata") or {}
        rsi = m.get("rsi_value")
        chg6 = m.get("btc_change_6h_avg")
        rsi_valid = m.get("rsi_valid", True)
        fired = t.get("signal_type")
        side = t.get("side")
        
        if rsi is None or chg6 is None or not rsi_valid:
            continue
            
        eligible = []
        if rsi < 30 and chg6 >= 1.5: eligible.append("VERY_STRONG_BUY")
        if rsi < 35 and chg6 >= 1.0: eligible.append("STRONG_BUY")
        if rsi < 45 and chg6 >= 0.5: eligible.append("MEDIUM_BUY")
        if rsi < 30: eligible.append("DIP")
        if chg6 >= 2.0: eligible.append("MOMENTUM_BUY")
        
        if rsi > 75 and chg6 <= -1.5: eligible.append("VERY_STRONG_SELL")
        if rsi > 70 and chg6 <= -1.0: eligible.append("STRONG_SELL")
        if rsi > 65 and chg6 <= -0.5: eligible.append("MEDIUM_SELL")
        if rsi > 75: eligible.append("TOP")
        if chg6 <= -2.0: eligible.append("MOMENTUM_SELL")
        
        # If multiple eligible, the one that didn't win is suppressed
        fired_key = f"{fired}_{side.upper()}" if fired and side else fired
        if len(eligible) > 1:
            for e in eligible:
                if e != fired_key and not (e == "DIP" and fired_key == "DIP"):
                    suppressed_counts[e] += 1

    for k, v in suppressed_counts.most_common():
        print(f"  {k:20s} {v}")

if __name__ == "__main__":
    main()
