#!/usr/bin/env python3
# m9_report.py - Calculate Overall & Per-Asset Wilson Lower Bound, PF, AvgR, MaxDD

import json, math
from collections import defaultdict

def wilson_lower(k, n, z=1.96):
    if n == 0: return 0.0
    p = k / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return center - half

def print_stats(label, trades):
    n = len(trades)
    if n == 0:
        print(f"\n--- {label} ---")
        print("No closed trades yet.")
        return

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    k = len(wins)
    
    wr = (k / n) * 100
    wilson_lo = wilson_lower(k, n) * 100
    
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0
    
    avg_r = sum(t["pnl"] for t in trades) / n
    
    # Simplified MaxDD calculation (absolute amount based)
    equity = 10000.0
    peak = equity
    max_dd = 0.0
    for t in trades:
        equity += (t["amount"] * (t["pnl"]/100))
        if equity > peak: peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd: max_dd = dd

    print(f"\n--- {label} ---")
    print(f"Trades (n): {n}")
    print(f"Win Rate: {wr:.1f}%")
    print(f"Wilson Lower 95%: {wilson_lo:.1f}% (Need > 36%)")
    print(f"Profit Factor: {pf:.2f} (Need > 1.2)")
    print(f"Expectancy: {avg_r:.2f}% (Need > 0.1R)")
    print(f"Max Drawdown: {max_dd:.1f}% (Need < 15%)")

def main():
    try:
        with open("paper_m9_trades.json") as f:
            state = json.load(f)
    except FileNotFoundError:
        print("paper_m9_trades.json not found.")
        return

    all_trades = [t for t in state["trades"] if t["status"] == "closed"]
    
    print(f"=== M9 Live Report (D-29 Gate) ===")
    print(f"Current Capital: {state['capital']:.2f} USDT")
    
    # Overall stats
    print_stats("OVERALL PORTFOLIO", all_trades)
    
    # Per-asset stats
    by_asset = defaultdict(list)
    for t in all_trades:
        by_asset[t["symbol"]].append(t)
        
    for symbol in ["ETHUSDT", "SUIUSDT", "SOLUSDT"]:
        print_stats(symbol, by_asset.get(symbol, []))

if __name__ == "__main__":
    main()
