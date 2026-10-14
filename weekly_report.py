#!/usr/bin/env python3
"""
weekly_report.py — گزارش وضعیت Stop Condition
read-only: هیچ فایلی رو تغییر نمی‌ده
"""
import json
from datetime import datetime, timezone
from collections import defaultdict

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
LOCK_DATE = "2026-10-14"       # تاریخ قفل Stop Condition
TARGET_DIP = 100
TARGET_REGIMES = 2
MIN_DAYS = 14
CODE_VERSIONS = ("paper_trade33", "paper_trade34")


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {fn}: {e}")
        return []


def days_since(date_str):
    d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - d).days


def dip_stats():
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    dips = [t for t in p + s
            if t.get("signal_type") == "DIP"
            and (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    closed = [t for t in dips if t.get("status") == "closed"]
    by_regime = defaultdict(int)
    for t in closed:
        reg = (t.get("metadata") or {}).get("regime_avg", "unknown")
        by_regime[reg] += 1
    return {"total": len(dips), "closed": len(closed), "by_regime": dict(by_regime)}


def top_stats():
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    tops = [t for t in p + s
            if t.get("signal_type") == "TOP"
            and (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    closed = [t for t in tops if t.get("status") == "closed"]
    net = sum((t.get("profit_net_toman") or 0) for t in closed)
    wins = sum(1 for t in closed if (t.get("profit_net_toman") or 0) > 0)
    return {"total": len(tops), "closed": len(closed), "net": net,
            "wr": (wins / len(closed) * 100) if closed else 0}


def momentum_stats():
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    ms = [t for t in p + s
          if t.get("signal_type") == "MOMENTUM"
          and (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    closed = [t for t in ms if t.get("status") == "closed"]
    net = sum((t.get("profit_net_toman") or 0) for t in closed)
    return {"total": len(ms), "closed": len(closed), "net": net}


def paper_stats():
    p = load(PAPER_FILE)
    closed = [t for t in p if t.get("status") == "closed"]
    net = sum((t.get("profit_net_toman") or 0) for t in closed)
    wins = sum(1 for t in closed if (t.get("profit_net_toman") or 0) > 0)
    opens = len([t for t in p if t.get("status") == "open"])
    return {"total": len(p), "closed": len(closed), "open": opens,
            "net": net, "wr": (wins / len(closed) * 100) if closed else 0}


def main():
    print("=" * 62)
    now = datetime.now(timezone.utc)
    print(f"WEEKLY REPORT — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 62)

    # Stop Condition progress
    d = dip_stats()
    closed_dips = d["closed"]
    regimes = [k for k in d["by_regime"].keys() if k != "unknown" and d["by_regime"][k] > 0]
    n_regimes = len(regimes)
    days = days_since(LOCK_DATE)

    print(f"\n[1] STOP CONDITION PROGRESS")
    print(f"  DIP closed:    {closed_dips:>4}/{TARGET_DIP}   ({closed_dips/TARGET_DIP*100:5.1f}%)")
    print(f"  Regimes:       {n_regimes:>4}/{TARGET_REGIMES}     {regimes}")
    print(f"  Days since:    {days:>4}/{MIN_DAYS}")
    ready = (closed_dips >= TARGET_DIP) and (n_regimes >= TARGET_REGIMES) and (days >= MIN_DAYS)
    if ready:
        print(f"  STATUS:        ✅ READY for final analysis")
    else:
        print(f"  STATUS:        ⏳ Waiting")

    # DIP by regime
    print(f"\n[2] DIP by regime")
    for reg in sorted(d["by_regime"].keys()):
        n = d["by_regime"][reg]
        print(f"  {reg:10s}: {n}")

    # Paper summary
    ps = paper_stats()
    print(f"\n[3] Paper")
    print(f"  Total={ps['total']} | Closed={ps['closed']} | Open={ps['open']}")
    print(f"  WR={ps['wr']:.1f}% | net={ps['net']:+.0f}")

    # TOP summary
    ts = top_stats()
    print(f"\n[4] TOP (cohort 33/34)")
    print(f"  Total={ts['total']} | Closed={ts['closed']}")
    print(f"  WR={ts['wr']:.1f}% | net={ts['net']:+.0f}")

    # MOMENTUM
    ms = momentum_stats()
    print(f"\n[5] MOMENTUM (cohort 33/34)")
    print(f"  Total={ms['total']} | Closed={ms['closed']} | net={ms['net']:+.0f}")

    print("\n" + "=" * 62)
    print("END — read-only")
    print("=" * 62)


if __name__ == "__main__":
    main()
