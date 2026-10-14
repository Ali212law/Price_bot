#!/usr/bin/env python3
"""
weekly_report.py v2 — گزارش وضعیت با شفافیت کامل
read-only: هیچ فایلی رو تغییر نمی‌ده
"""
import json
from datetime import datetime, timezone
from collections import defaultdict, Counter

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
LOCK_DATE = "2026-10-14"
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


def extract_dates(trades):
    """تاریخ‌های entry_time (فقط بخش YYYY-MM-DD)"""
    dates = set()
    for t in trades:
        et = t.get("entry_time", "")
        if et and len(et) >= 10:
            dates.add(et[:10])
    return dates


def all_cohort_trades():
    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)
    all_t = [t for t in p + s
             if (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    return p, s, all_t


def main():
    print("=" * 62)
    now = datetime.now(timezone.utc)
    print(f"WEEKLY REPORT v2 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 62)
    print(f"Lock date: {LOCK_DATE}")
    print(f"Cohort: {CODE_VERSIONS}")

    p, s, all_t = all_cohort_trades()

    # ============================================
    # ۱. STOP CONDITION
    # ============================================
    print(f"\n[1] STOP CONDITION PROGRESS")
    print(f"  ──────────────────────────────")

    dips = [t for t in all_t if t.get("signal_type") == "DIP"]
    dips_closed = [t for t in dips if t.get("status") == "closed"]
    dips_open = [t for t in dips if t.get("status") == "open"]

    by_regime = defaultdict(list)
    for t in dips_closed:
        reg = (t.get("metadata") or {}).get("regime_avg", "unknown")
        by_regime[reg].append(t)

    n_regimes = len([r for r in by_regime.keys() if r != "unknown"])
    days = days_since(LOCK_DATE)

    print(f"  DIP total:     {len(dips):>4}  (= closed {len(dips_closed)} + open {len(dips_open)})")
    print(f"  DIP closed:    {len(dips_closed):>4}/{TARGET_DIP}   ({len(dips_closed)/TARGET_DIP*100:5.1f}%)")
    print(f"  Regimes:       {n_regimes:>4}/{TARGET_REGIMES}     {sorted(by_regime.keys())}")
    print(f"  Days elapsed:  {days:>4}/{MIN_DAYS}   (تقویمی از تاریخ قفل)")
    ready = (len(dips_closed) >= TARGET_DIP) and (n_regimes >= TARGET_REGIMES) and (days >= MIN_DAYS)
    status = "✅ READY" if ready else "⏳ Waiting"
    print(f"  STATUS:        {status}")
    print(f"  ──────────────────────────────")
    print(f"  * معیار ۱۰۰ DIP = closed فقط، روزها = تقویمی")

    # ============================================
    # ۲. DIP by regime (با روزهای مستقل)
    # ============================================
    print(f"\n[2] DIP closed by regime")
    for reg in sorted(by_regime.keys()):
        trades = by_regime[reg]
        dates = extract_dates(trades)
        pnls = [(t.get("profit_net_toman") or 0) for t in trades]
        net = sum(pnls)
        wr = sum(1 for x in pnls if x > 0) / len(pnls) * 100 if pnls else 0
        print(f"  {reg:10s}: n={len(trades):3d} | days={len(dates):2d} | WR={wr:5.1f}% | net={net:+8.0f}")

    # ============================================
    # ۳. Paper Summary
    # ============================================
    print(f"\n[3] Paper")
    closed_p = [t for t in p if t.get("status") == "closed"]
    open_p = [t for t in p if t.get("status") == "open"]
    net_p = sum((t.get("profit_net_toman") or 0) for t in closed_p)
    wins_p = sum(1 for t in closed_p if (t.get("profit_net_toman") or 0) > 0)
    wr_p = wins_p / len(closed_p) * 100 if closed_p else 0
    print(f"  Total={len(p)} | Closed={len(closed_p)} | Open={len(open_p)}")
    print(f"  WR={wr_p:.1f}% | net={net_p:+.0f} (بعد از هزینه 0.6%)")

    # ============================================
    # ۴. TOP Summary
    # ============================================
    print(f"\n[4] TOP (cohort 33/34)")
    tops = [t for t in all_t if t.get("signal_type") == "TOP"]
    tops_closed = [t for t in tops if t.get("status") == "closed"]
    tops_open = [t for t in tops if t.get("status") == "open"]
    net_t = sum((t.get("profit_net_toman") or 0) for t in tops_closed)
    wins_t = sum(1 for t in tops_closed if (t.get("profit_net_toman") or 0) > 0)
    wr_t = wins_t / len(tops_closed) * 100 if tops_closed else 0
    print(f"  Total={len(tops)} | Closed={len(tops_closed)} | Open={len(tops_open)}")
    print(f"  WR={wr_t:.1f}% | net={net_t:+.0f}")

    # ============================================
    # ۵. MOMENTUM Summary
    # ============================================
    print(f"\n[5] MOMENTUM (cohort 33/34)")
    moms = [t for t in all_t if t.get("signal_type") == "MOMENTUM"]
    moms_closed = [t for t in moms if t.get("status") == "closed"]
    net_m = sum((t.get("profit_net_toman") or 0) for t in moms_closed)
    print(f"  Total={len(moms)} | Closed={len(moms_closed)} | net={net_m:+.0f}")

    # ============================================
    # ۶. Rejection breakdown
    # ============================================
    print(f"\n[6] Rejection breakdown (all cohort)")
    rejects = [t for t in s if t.get("shadow_type", "").startswith("rejected_")]
    rej_counter = Counter(t.get("shadow_type") for t in rejects)
    for k, v in rej_counter.most_common():
        print(f"  {k:35s} {v}")

    # ============================================
    # ۷. Data quality
    # ============================================
    print(f"\n[7] Data quality")
    missing_meta = [t for t in all_t if not t.get("metadata")]
    missing_chg = [t for t in all_t
                   if (t.get("metadata") or {}).get("btc_change_24h_avg") is None]
    missing_rsi = [t for t in all_t
                   if (t.get("metadata") or {}).get("rsi_value") is None]
    print(f"  Missing metadata:      {len(missing_meta)}")
    print(f"  Missing chg24h_avg:    {len(missing_chg)}")
    print(f"  Missing rsi_value:     {len(missing_rsi)}")

    # ============================================
    # ۸. Signal distribution (فعال vs خاموش)
    # ============================================
    print(f"\n[8] Signal distribution (cohort 33/34)")
    sig_counter = Counter(t.get("signal_type", "?") for t in all_t)
    all_signals = ["DIP", "TOP", "MOMENTUM", "VERY_STRONG", "STRONG", "MEDIUM"]
    for sig in all_signals:
        n = sig_counter.get(sig, 0)
        status = "✅" if n > 0 else "❌"
        print(f"  {status} {sig:15s} {n}")

    print("\n" + "=" * 62)
    print("END — read-only")
    print("=" * 62)


if __name__ == "__main__":
    main()
