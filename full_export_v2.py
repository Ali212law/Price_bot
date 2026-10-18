#!/usr/bin/env python3
# full_export_v2.py — گزارش‌گیر نسخه ۲ | 2026-10-18 | AI سوم (هوشا) به درخواست Ali
# فایل جدید است؛ هیچ‌یک از سه فایل قفل‌شده را تغییر نمی‌دهد.
# شمارنده رسمی M2: فقط ترید واقعی Paper35 با status=closed و signal_type=DIP
# Shadow و rejected هرگز در شمارنده ۱۰۰ حساب نمی‌شوند. Cohortها جدا چاپ می‌شوند.

import json
from collections import Counter
from datetime import datetime, timezone

FILES = {
    "paper_33_34":  "paper_trades.json",
    "paper_35":     "paper_trades35.json",
    "shadow_33_34": "shadow_trades.json",
    "shadow_35":    "shadow_trades35.json",
    "anchor_33_34": "time_anchor.json",
    "anchor_35":    "time_anchor35.json",
}
TARGET_DIP = 100
LOCK_DATE_FALLBACK = "2026-10-17"
CADENCE_MIN_35 = 15          # cron: '14,29,44,59 * * * *'
STALE_AFTER_MIN = 90         # آستانه هشدار کهنگی anchor35

def load(fn):
    try:
        with open(fn, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None

def now_utc():
    return datetime.now(timezone.utc)

def cohort_block(title, records):
    print("\n--- %s ---" % title)
    print("records: %d" % len(records))
    if not records:
        print("EMPTY")
        return
    dips = [t for t in records if str(t.get("signal_type") or "").upper() == "DIP"]
    dips_closed = [t for t in dips if str(t.get("status") or "").lower() == "closed"]
    open_trades = [t for t in records if str(t.get("status") or "").lower() == "open"]
    st = Counter(str(t.get("status") or "?") for t in records)
    print("DIP total (records): %d" % len(dips))
    print("DIP closed (real trades): %d" % len(dips_closed))
    print("open trades (all types): %d" % len(open_trades))
    print("status distribution: %s" % dict(st))

def anchor_block(title, fn, watch_stale=False):
    print("\n--- %s (%s) ---" % (title, fn))
    try:
        with open(fn, encoding="utf-8") as f:
            a = json.load(f)
    except Exception:
        print("MISSING or unreadable")
        return {}
    print(json.dumps(a, ensure_ascii=False))
    ts = parse_ts(a.get("last_run_utc") or a.get("last_run") or "")
    if not ts:
        print("!! anchor timestamp not parseable")
        return a
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_min = (now_utc() - ts).total_seconds() / 60.0
    print("anchor age: %.0f minutes" % age_min)
    if watch_stale and age_min > STALE_AFTER_MIN:
        print("!! WARNING: anchor35 stale (> %d min, cadence %d min). "
              "Persistence failure suspected — check paper_trade35.yml commit step "
              "and GitHub API errors." % (STALE_AFTER_MIN, CADENCE_MIN_35))
    return a

def main():
    print("=" * 62)
    print("FULL EXPORT v2 — %s" % now_utc().strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 62)

    p34 = load(FILES["paper_33_34"])
    p35 = load(FILES["paper_35"])
    s34 = load(FILES["shadow_33_34"])
    s35 = load(FILES["shadow_35"])

    print("\nSECTION 1 — DATASETS (per file, no mixing)")
    cohort_block("COHORT 33/34 PAPER (paper_trades.json)", p34)
    cohort_block("COHORT 35 PAPER M2 (paper_trades35.json)", p35)
    cohort_block("SHADOW 33/34 (shadow_trades.json) — NOT counted toward M2", s34)
    cohort_block("SHADOW 35 v5.3 (shadow_trades35.json) — NOT counted toward M2", s35)

    print("\nSECTION 2 — M2 STOP CONDITION (official counter)")
    print("Definition (locked): only REAL paper trades of Paper35, "
          "status=closed, signal_type=DIP; target %d; AND min 14 days from lock." % TARGET_DIP)
    dips35_closed = [t for t in p35
                     if str(t.get("signal_type") or "").upper() == "DIP"
                     and str(t.get("status") or "").lower() == "closed"]
    print("Paper35 DIP closed: %d/%d" % (len(dips35_closed), TARGET_DIP))
    a35 = anchor_block("anchor_35", FILES["anchor_35"], watch_stale=True)
    lock = str(a35.get("lock_date") or LOCK_DATE_FALLBACK)[:10]
    try:
        d0 = datetime.strptime(lock, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days = (now_utc() - d0).days
        met = days >= 14
        print("lock_date: %s | days elapsed: %d | min required: 14 (%s)"
              % (lock, days, "met" if met else "not met"))
        triggered = len(dips35_closed) >= TARGET_DIP and met
        print("stop condition (AND): %s" % ("TRIGGERED" if triggered else "ACTIVE"))
    except Exception:
        print("lock_date parse failed")

    print("\nSECTION 3 — OLD-COHORT ANCHOR (33/34, reference only)")
    anchor_block("anchor_33_34", FILES["anchor_33_34"])

    print("\nNOTE: WR/Net/regimes are NOT computed here by design — "
          "field-schema samples pending; will be added in weekly_report v4.")
    print("NOTE: shadow records are NEVER counted toward the M2 DIP counter.")

if __name__ == "__main__":
    main()
