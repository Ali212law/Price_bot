#!/usr/bin/env python3
"""
stat_analysis.py — Bootstrap CI analysis for DIP filter
read-only: هیچ فایلی رو تغییر نمی‌ده
"""
import json
import random
from collections import defaultdict

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
THRESHOLD = -0.5
N_RESAMPLES = 1000
CI_LEVEL = 95
RANDOM_SEED = 42


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {fn}: {e}")
        return []


def bootstrap_ci(values, n=N_RESAMPLES, ci=CI_LEVEL):
    if len(values) < 3:
        return None, None
    random.seed(RANDOM_SEED)
    means = []
    for _ in range(n):
        sample = [random.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int((100 - ci) / 2 / 100 * n)]
    hi = means[int((100 - (100 - ci) / 2) / 100 * n) - 1]
    return round(lo, 1), round(hi, 1)


def analyze_group(trades, label):
    closed = [t for t in trades if t.get("status") == "closed"]
    pnls = [(t.get("profit_net_toman") or 0) for t in closed]
    if not pnls:
        print(f"  {label}: n=0")
        return {"n": 0, "net": 0, "wr": 0, "ci": (None, None)}

    n = len(pnls)
    net = sum(pnls)
    wins = sum(1 for x in pnls if x > 0)
    wr = wins / n * 100
    ci_lo, ci_hi = bootstrap_ci(pnls)

    print(f"  {label}:")
    print(f"    n={n} | WR={wr:.1f}% | net={net:+.0f}")
    print(f"    avg={net/n:+.1f} | CI95 on mean=[{ci_lo}, {ci_hi}]")
    return {"n": n, "net": net, "wr": wr, "ci": (ci_lo, ci_hi), "avg": net/n}


def main():
    print("=" * 62)
    print("STAT ANALYSIS — DIP filter bootstrap CI")
    print(f"Threshold: chg24h_avg < {THRESHOLD}")
    print("=" * 62)

    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)

    # همه DIP با metadata جدید
    dips = [t for t in p + s
            if t.get("signal_type") == "DIP"
            and (t.get("metadata") or {}).get("code_version") in ("paper_trade33", "paper_trade34")]

    closed = [t for t in dips if t.get("status") == "closed"]
    print(f"\n[1] Total DIP (paper_trade33/34): {len(dips)}")
    print(f"    Closed: {len(closed)}")

    if not closed:
        print("No closed DIP. Exit.")
        return

    # گروه‌بندی
    baseline = closed
    filtered = []
    removed = []
    for t in closed:
        m = t.get("metadata") or {}
        chg = m.get("btc_change_24h_avg")
        if chg is None or chg >= THRESHOLD:
            filtered.append(t)
        else:
            removed.append(t)

    print(f"\n[2] Baseline vs Filtered")
    print(f"  Baseline (all):        n={len(baseline)}")
    print(f"  Filtered (keep):       n={len(filtered)}")
    print(f"  Removed (chg<{THRESHOLD}): n={len(removed)}")

    print(f"\n[3] Bootstrap CI (95%)")
    b = analyze_group(baseline, "BASELINE ")
    f = analyze_group(filtered, "FILTERED ")
    r = analyze_group(removed, "REMOVED  ")

    print(f"\n[4] Decision hint")
    if b["ci"][0] is not None and f["ci"][0] is not None:
        b_lo, b_hi = b["ci"]
        f_lo, f_hi = f["ci"]
        overlap = not (f_hi < b_lo or b_hi < f_lo)
        if overlap:
            print("  [X] CIs overlap -> نتيجه نامعلوم")
        else:
            print("  [OK] CIs do NOT overlap -> تفاوت معنادار")

    print(f"\n[5] Regime breakdown")
    by_regime = defaultdict(list)
    for t in closed:
        m = t.get("metadata") or {}
        reg = m.get("regime_avg", "unknown")
        by_regime[reg].append(t)

    for reg in sorted(by_regime.keys()):
        trades = by_regime[reg]
        pnls = [(t.get("profit_net_toman") or 0) for t in trades]
        net = sum(pnls)
        wr = sum(1 for x in pnls if x > 0) / len(pnls) * 100 if pnls else 0
        print(f"  {reg:10s}: n={len(trades):3d} | WR={wr:5.1f}% | net={net:+8.0f}")

    # Stop condition check
    print(f"\n[6] Stop condition check")
    n_dips = len(closed)
    n_regimes = len([r for r in by_regime.keys() if r != "unknown"])
    print(f"  DIP closed: {n_dips}/100")
    print(f"  Regimes:    {n_regimes}/2")
    if n_dips >= 100 and n_regimes >= 2:
        print("  [OK] STOP CONDITION MET")
    else:
        print(f"  ... Still waiting")

    print("\n" + "=" * 62)
    print("END — read-only")
    print("=" * 62)


if __name__ == "__main__":
    main()
