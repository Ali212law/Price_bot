#!/usr/bin/env python3
# m9_report.py - Calculate Wilson Lower Bound, PF, AvgR, MaxDD for M9
import json, math

def wilson_lower(k, n, z=1.96):
    if n == 0: return 0.0
    p = k / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return center - half

def main():
    with open("paper_m9_trades.json") as f:
        state = json.load(f)
        
    trades = [t for t in state["trades"] if t["status"] == "closed"]
    n = len(trades)
    if n == 0:
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
    
    # Simplified MaxDD calculation
    equity = 10000.0
    peak = equity
    max_dd = 0.0
    for t in trades:
        equity += (t["amount"] * (t["pnl"]/100))
        if equity > peak: peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd: max_dd = dd
        
    print(f"=== M9 Live Report (D-29 Gate) ===")
    print(f"Total Closed Trades (n): {n}")
    print(f"Win Rate (WR): {wr:.1f}%")
    print(f"Wilson Lower 95%: {wilson_lo:.1f}% (Need > 36%)")
    print(f"Profit Factor (PF): {pf:.2f} (Need > 1.2)")
    print(f"Expectancy (Avg R): {avg_r:.2f}% (Need > 0.1R)")
    print(f"Max Drawdown (MaxDD): {max_dd:.1f}% (Need < 15%)")
    print(f"Current Capital: {state['capital']:.2f} USDT")

if __name__ == "__main__":
    main()
