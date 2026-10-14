#!/usr/bin/env python3
"""
stat_analysis_top.py — تحلیل TOP signal (offline, read-only)
"""
import json
import random
from collections import defaultdict

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
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


def stats(trades):
    closed = [t for t in trades if t.get("status") == "closed"]
    pnls = [(t.get("profit_net_toman") or 0) for t in closed]
    if not pnls:
        return {"n": 0, "net": 0, "wr": 0, "avg": 0, "ci": (None, None)}
    n = len(pnls)
    net = sum(pnls)
    wins = sum(1 for x in pnls if x > 0)
    ci = bootstrap_ci(pnls)
    return {"n": n, "net": net, "wr": wins/n*100, "avg": net/n, "ci": ci}


def show(label, s):
    if s["n"] == 0:
        print(f"  {label}: n=0")
        return
    print(f"  {label}:")
    print(f"    n={s['n']} | WR={s['wr']:.1f}% | net={s['net']:+.0f} | avg={s['avg']:+.1f}")
    if s["ci"][0] is not None:
        print(f"    CI95 on mean = [{s['ci'][0]}, {s['ci'][1]}]")


def main():
    print("=" * 62)
    print("STAT ANALYSIS — TOP signal (descriptive)")
    print("=" * 62)

    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)

    # TOPها: Paper + Shadow top_only (metadata جدید)
    tops_p = [t for t in p if t.get("signal_type") == "TOP"
              and (t.get("metadata") or {}).get("code_version") in ("paper_trade33", "paper_trade34")]
    tops_s = [t for t in s if t.get("signal_type") == "TOP"
              and (t.get("metadata") or {}).get("code_version") in ("paper_trade33", "paper_trade34")]

    all_tops = tops_p + tops_s
    closed = [t for t in all_tops if t.get("status") == "closed"]

    print(f"\n[1] TOP inventory")
    print(f"  Paper TOP:                {len(tops_p)} (closed={len([t for t in tops_p if t.get('status')=='closed'])})")
    print(f"  Shadow TOP (all):         {len(tops_s)}")
    from collections import Counter
    print(f"  Shadow TOP by type:       {dict(Counter(t.get('shadow_type','?') for t in tops_s))}")
    print(f"  Total closed:             {len(closed)}")

    if not closed:
        print("No closed TOP. Exit.")
        return

    # Baseline
    print(f"\n[2] Baseline (all closed)")
    b = stats(closed)
    show("ALL TOP", b)

    # Paper vs Shadow breakdown
    print(f"\n[3] Paper vs Shadow (top_only)")
    p_closed = [t for t in tops_p if t.get("status") == "closed"]
    s_closed = [t for t in tops_s if t.get("status") == "closed"]
    show("Paper TOP ", stats(p_closed))
    show("Shadow TOP", stats(s_closed))

    # Regime breakdown
    print(f"\n[4] Regime breakdown")
    by_regime = defaultdict(list)
    for t in closed:
        m = t.get("metadata") or {}
        reg = m.get("regime_avg", "unknown")
        by_regime[reg].append(t)
    for reg in sorted(by_regime.keys()):
        show(f"regime={reg}", stats(by_regime[reg]))

    # Chg24h breakdown (برای TOP، صعودی مهمه)
    print(f"\n[5] chg24h_avg breakdown (TOP)")
    buckets = {
        "bull (chg24 > +1.5)": [],
        "chop-up (+0.5 to +1.5)": [],
        "range (-0.5 to +0.5)": [],
        "chop-down (-1.5 to -0.5)": [],
        "bear (chg24 < -1.5)": [],
        "no_data": [],
    }
    for t in closed:
        m = t.get("metadata") or {}
        c = m.get("btc_change_24h_avg")
        if c is None:
            buckets["no_data"].append(t)
        elif c > 1.5:
            buckets["bull (chg24 > +1.5)"].append(t)
        elif c > 0.5:
            buckets["chop-up (+0.5 to +1.5)"].append(t)
        elif c >= -0.5:
            buckets["range (-0.5 to +0.5)"].append(t)
        elif c >= -1.5:
            buckets["chop-down (-1.5 to -0.5)"].append(t)
        else:
            buckets["bear (chg24 < -1.5)"].append(t)
    for name in ["bull (chg24 > +1.5)", "chop-up (+0.5 to +1.5)", "range (-0.5 to +0.5)",
                 "chop-down (-1.5 to -0.5)", "bear (chg24 < -1.5)", "no_data"]:
        show(name, stats(buckets[name]))

    # Sample with times
    print(f"\n[6] Sample closed TOP (last 10)")
    sorted_closed = sorted(closed, key=lambda t: t.get("entry_time", ""))
    for t in sorted_closed[-10:]:
        m = t.get("metadata") or {}
        et = t.get("entry_time", "?")[:19]
        cv = m.get("code_version", "?")
        chg = m.get("btc_change_24h_avg")
        reg = m.get("regime_avg", "?")
        st = t.get("status")
        n = t.get("profit_net_toman") or 0
        chg_s = f"{chg:+.2f}" if chg is not None else "None"
        print(f"  {et} | {cv:14s} | chg24={chg_s:6s} | reg={reg:6s} | net={n:+.0f}")

    print("\n" + "=" * 62)
    print("END — read-only")
    print("=" * 62)


if __name__ == "__main__":
    main()
