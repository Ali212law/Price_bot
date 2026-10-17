#!/usr/bin/env python3
"""
weekly_report.py v3 — Separate Cohorts (33/34 vs 35)
"""
import json
from datetime import datetime, timezone
from collections import defaultdict, Counter

PAPER_FILE = "paper_trades.json"       # Cohort 33/34
PAPER_35_FILE = "paper_trades35.json"  # Cohort 35 (M2)
SHADOW_FILE = "shadow_trades.json"     # Cohort 33/34 shadow
CODE_VERSIONS_OLD = ("paper_trade33", "paper_trade34")
CODE_VERSION_35 = "paper_trade35"

TARGET_DIP = 100
TARGET_REGIMES = 2
MIN_DAYS = 14

def load(fn):
    try:
        with open(fn) as f: return json.load(f)
    except: return []

def days_since(date_str):
    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except: return 0

def get_cohort_stats(trades, label, versions):
    cohort = [t for t in trades if (t.get("metadata") or {}).get("code_version") in versions]
    closed = [t for t in cohort if t.get("status") == "closed"]
    opens = [t for t in cohort if t.get("status") == "open"]
    
    if not cohort:
        print(f"\n[{label}] No trades yet.")
        return

    pnls = [t.get("profit_net_toman", 0) for t in closed]
    wins = sum(1 for x in pnls if x > 0)
    net = sum(pnls)
    wr = (wins/len(closed)*100) if closed else 0

    print(f"\n[{label}]")
    print(f"  Total: {len(cohort)} | Closed: {len(closed)} | Open: {len(opens)}")
    print(f"  WR: {wr:.1f}% | Net: {net:+.0f} Toman")

    dips_closed = [t for t in closed if t.get("signal_type") == "DIP"]
    by_regime = defaultdict(int)
    for t in dips_closed:
        r = (t.get("metadata") or {}).get("regime_avg", "unknown")
        by_regime[r] += 1
        
    print(f"  DIP Closed: {len(dips_closed)}/{TARGET_DIP}")
    print(f"  Regimes: {dict(by_regime)}")

def main():
    print(f"WEEKLY REPORT v3 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    p = load(PAPER_FILE)
    p35 = load(PAPER_35_FILE)

    # Cohort 33/34
    get_cohort_stats(p, "COHORT 33/34 (Old)", CODE_VERSIONS_OLD)

    # Cohort 35 (M2)
    get_cohort_stats(p35, "COHORT 35 (M2)", (CODE_VERSION_35,))

    # Shadow Stats
    s = load(SHADOW_FILE)
    print(f"\n[SHADOW 33/34]")
    print(f"  Total: {len(s)}")

if __name__ == "__main__":
    main()
