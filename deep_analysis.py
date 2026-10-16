#!/usr/bin/env python3
"""
deep_analysis.py — تحلیل عمیق داده‌های موجود (read-only)
- RSI binning
- chg24h binning
- Hour-of-day pattern
- Cluster bootstrap (روز-محور)
- Running WR
"""
import json
import random
from collections import defaultdict
from datetime import datetime

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
CODE_VERSIONS = ("paper_trade33", "paper_trade34")
N_RESAMPLES = 1000
RANDOM_SEED = 42


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {fn}: {e}")
        return []


def get_dip_closed():
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    dips = [t for t in p + s
            if t.get("signal_type") == "DIP"
            and t.get("status") == "closed"
            and (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    return dips


def get_day(t):
    et = t.get("entry_time", "")
    return et[:10] if len(et) >= 10 else "?"


def get_hour(t):
    et = t.get("entry_time", "")
    if len(et) >= 13:
        try:
            return int(et[11:13])
        except ValueError:
            return None
    return None


def stats(pnls):
    if not pnls:
        return {"n": 0, "wr": 0, "net": 0, "avg": 0}
    n = len(pnls)
    net = sum(pnls)
    wins = sum(1 for x in pnls if x > 0)
    return {"n": n, "wr": wins/n*100, "net": net, "avg": net/n}


def show_row(label, pnls):
    if not pnls:
        print(f"  {label:22s} n=0")
        return
    s = stats(pnls)
    print(f"  {label:22s} n={s['n']:2d} | WR={s['wr']:5.1f}% | net={s['net']:+7.0f} | avg={s['avg']:+7.1f}")


def cluster_bootstrap_by_day(dips, value_fn, n=N_RESAMPLES, ci=95):
    """bootstrap با خوشه‌بندی روز"""
    random.seed(RANDOM_SEED)
    by_day = defaultdict(list)
    for t in dips:
        by_day[get_day(t)].append(value_fn(t))
    days = list(by_day.keys())
    if len(days) < 3:
        return None, None, "insufficient_days"
    
    means = []
    for _ in range(n):
        sampled_days = [random.choice(days) for _ in days]
        vals = []
        for d in sampled_days:
            vals.extend(by_day[d])
        if vals:
            means.append(sum(vals) / len(vals))
    
    if not means:
        return None, None, "no_means"
    
    means.sort()
    lo = means[int((100 - ci) / 2 / 100 * n)]
    hi = means[int((100 - (100 - ci) / 2) / 100 * n) - 1]
    return round(lo, 1), round(hi, 1), "ok"


def main():
    print("=" * 70)
    print("DEEP ANALYSIS — cohort 33/34")
    print(f"Run: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    dips = get_dip_closed()
    print(f"\nDIP closed: {len(dips)}")
    if not dips:
        return

    # ============================
    # 1. RSI Binning
    # ============================
    print(f"\n[1] RSI binning (DIP)")
    bins = [(0, 20), (20, 25), (25, 30), (30, 35), (35, 100), (None, None)]
    labels = ["RSI  0-20", "RSI 20-25", "RSI 25-30", "RSI 30-35", "RSI 35+", "RSI None"]
    for (lo, hi), label in zip(bins, labels):
        pnls = []
        for t in dips:
            rsi = (t.get("metadata") or {}).get("rsi_value")
            if rsi is None:
                if label == "RSI None":
                    pnls.append(t.get("profit_net_toman") or 0)
            elif lo is not None and lo <= rsi < hi:
                pnls.append(t.get("profit_net_toman") or 0)
        show_row(label, pnls)

    # ============================
    # 2. chg24h Binning
    # ============================
    print(f"\n[2] chg24h_avg binning (DIP)")
    bins = [(0.5, 100), (0, 0.5), (-0.5, 0), (-1.0, -0.5), (-1.5, -1.0), (-2.0, -1.5), (-100, -2.0), (None, None)]
    labels = ["chg24 > +0.5", "chg24 0 to +0.5", "chg24 -0.5 to 0",
              "chg24 -1.0 to -0.5", "chg24 -1.5 to -1.0", "chg24 -2.0 to -1.5",
              "chg24 < -2.0", "chg24 None"]
    for (lo, hi), label in zip(bins, labels):
        pnls = []
        for t in dips:
            c = (t.get("metadata") or {}).get("btc_change_24h_avg")
            if c is None:
                if label == "chg24 None":
                    pnls.append(t.get("profit_net_toman") or 0)
            elif lo is not None and lo <= c < hi:
                pnls.append(t.get("profit_net_toman") or 0)
        show_row(label, pnls)

    # ============================
    # 3. Hour of day
    # ============================
    print(f"\n[3] Hour-of-day (UTC) — بصورت 4 گروه")
    hour_buckets = {
        "00-06 UTC": [],
        "06-12 UTC": [],
        "12-18 UTC": [],
        "18-24 UTC": [],
    }
    for t in dips:
        h = get_hour(t)
        if h is None:
            continue
        pnl = t.get("profit_net_toman") or 0
        if h < 6:
            hour_buckets["00-06 UTC"].append(pnl)
        elif h < 12:
            hour_buckets["06-12 UTC"].append(pnl)
        elif h < 18:
            hour_buckets["12-18 UTC"].append(pnl)
        else:
            hour_buckets["18-24 UTC"].append(pnl)
    for label, pnls in hour_buckets.items():
        show_row(label, pnls)

    # ============================
    # 4. Cluster bootstrap (day-based)
    # ============================
    print(f"\n[4] Cluster bootstrap (day-based)")
    by_day = defaultdict(list)
    for t in dips:
        by_day[get_day(t)].append(t.get("profit_net_toman") or 0)
    print(f"  Independent days: {len(by_day)}")
    for d in sorted(by_day.keys()):
        pnls = by_day[d]
        s = stats(pnls)
        print(f"    {d}: n={s['n']:2d} | net={s['net']:+7.0f} | avg={s['avg']:+7.1f}")

    lo, hi, status = cluster_bootstrap_by_day(dips, lambda t: t.get("profit_net_toman") or 0)
    if status == "ok":
        print(f"  Cluster CI95 on mean: [{lo}, {hi}]")
    else:
        print(f"  Cluster bootstrap: {status}")

    # ============================
    # 5. Running WR
    # ============================
    print(f"\n[5] Running WR (ترتیبی)")
    sorted_dips = sorted(dips, key=lambda t: t.get("entry_time", ""))
    cum_wins = 0
    cum_n = 0
    step = max(1, len(sorted_dips) // 10)
    print(f"  n    | cum WR")
    for i, t in enumerate(sorted_dips, 1):
        pnl = t.get("profit_net_toman") or 0
        cum_n += 1
        if pnl > 0:
            cum_wins += 1
        if i % step == 0 or i == len(sorted_dips):
            wr = cum_wins / cum_n * 100
            print(f"  {cum_n:3d}  | {wr:5.1f}%")

    # ============================
    # 6. Long vs Short holding
    # ============================
    print(f"\n[6] Holding duration (ساعت)")
    durations = []
    for t in dips:
        et = t.get("entry_time", "")
        xt = t.get("exit_time", "")
        if not et or not xt:
            continue
        try:
            d = (datetime.fromisoformat(xt) - datetime.fromisoformat(et)).total_seconds() / 3600
            durations.append((d, t.get("profit_net_toman") or 0))
        except Exception:
            continue
    if durations:
        short = [p for d, p in durations if d < 12]
        medium = [p for d, p in durations if 12 <= d < 48]
        long_ = [p for d, p in durations if d >= 48]
        show_row("<12h", short)
        show_row("12-48h", medium)
        show_row(">=48h", long_)

    print("\n" + "=" * 70)
    print("END — read-only")
    print("=" * 70)


if __name__ == "__main__":
    main()
