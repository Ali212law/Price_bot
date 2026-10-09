#!/usr/bin/env python3
"""
analyze_rejected.py — ابزار تحلیل موقت (read-only)
هدف: جداسازی top_only به mirror/standalone + تحلیل rejected_*
هیچ فایلی نوشته نمی‌شود.
"""
import json
from datetime import datetime
from collections import defaultdict

SHADOW_FILE = "shadow_trades.json"
PAPER_FILE = "paper_trades.json"
MATCH_TIME_TOLERANCE_SEC = 10


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {fn}: {e}")
        return []


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def match_mirror(shadow, papers):
    st = parse_time(shadow.get("entry_time") or shadow.get("time"))
    sp = shadow.get("entry_price")
    if not st or sp is None:
        return None
    for p in papers:
        pt = parse_time(p.get("entry_time") or p.get("time"))
        pp = p.get("entry_price")
        if not pt or pp is None:
            continue
        dt = abs((st - pt).total_seconds())
        if dt <= MATCH_TIME_TOLERANCE_SEC and abs(sp - pp) < 1.0:
            return p
    return None


def calc_stats(trades, label):
    closed = [t for t in trades if t.get("status") == "closed"]
    n = len(closed)
    opens = len([t for t in trades if t.get("status") == "open"])
    if n == 0:
        print(f"  {label}: n=0 (open={opens})")
        return
    pnls = [(t.get("profit_net_toman") or 0) for t in closed]
    wins = [x for x in pnls if x > 0]
    net = sum(pnls)
    wr = len(wins) / n * 100
    avg = net / n
    print(f"  {label}:")
    print(f"    n={n} (open={opens}) | WR={wr:.0f}% | net={net:+.0f} | avg={avg:+.0f}")
    print(f"    best={max(pnls):+.0f} | worst={min(pnls):+.0f}")


def main():
    shadows = load(SHADOW_FILE)
    papers = load(PAPER_FILE)

    print("=" * 62)
    print(f"ANALYZE REJECTED — {datetime.now().isoformat()}")
    print(f"Shadow: {len(shadows)} | Paper: {len(papers)}")
    print("=" * 62)

    by_type = defaultdict(list)
    for s in shadows:
        by_type[s.get("shadow_type", "unknown")].append(s)

    print("\n[1] Shadow by type:")
    for k in sorted(by_type.keys()):
        print(f"  {k:32s} {len(by_type[k])}")

    top_only = by_type.get("top_only", [])
    mirror, standalone = [], []
    for s in top_only:
        m = match_mirror(s, papers)
        (mirror if m else standalone).append(s)

    print(f"\n[2] top_only split:")
    print(f"  mirror (Paper قبول کرد)      {len(mirror)}")
    print(f"  standalone (Paper رد کرد)   {len(standalone)}")

    print(f"\n[3] آمار top_only:")
    calc_stats(mirror, "mirror       ")
    calc_stats(standalone, "standalone   ")
    calc_stats(top_only, "کل top_only  ")

    for rt in sorted(by_type.keys()):
        if rt.startswith("rejected_already"):
            print(f"\n[4] {rt}:")
            calc_stats(by_type[rt], rt)

    paper_top = [p for p in papers if p.get("signal_type") == "TOP"]
    print(f"\n[5] Paper TOP (پذیرفته‌شده‌ها):")
    calc_stats(paper_top, "Paper TOP")

    by_ver = defaultdict(list)
    for s in shadows:
        v = (s.get("metadata") or {}).get("code_version", "unknown")
        by_ver[v].append(s)
    print(f"\n[6] Shadow by code_version:")
    for k in sorted(by_ver.keys()):
        print(f"  {k:20s} {len(by_ver[k])}")

    print("\n" + "=" * 62)
    print("END — read-only, هیچ فایلی نوشته نشد")
    print("=" * 62)


if __name__ == "__main__":
    main()
