#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze6.py - تحلیل جامع Paper + Shadow + Iran News
"""

import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
F_PAPER  = BASE_DIR / "paper_trades.json"
F_SHADOW = BASE_DIR / "shadow_trades.json"
F_IRAN   = BASE_DIR / "iran_news_data.json"
F_GLOBAL = BASE_DIR / "news_history.json"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fmt(v, d=2):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return str(v)


def fnum(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def sub(title):
    print()
    print(f"--- {title} ---")


def get_pnl(t):
    v = t.get("profit_net_toman")
    if v is not None and v != 0:
        return fnum(v)
    v = t.get("net_pnl")
    if v is not None:
        return fnum(v)
    return 0.0


def summarize(trades, label):
    total = len(trades)
    open_t = [t for t in trades if t.get("status") == "open"]
    closed = [t for t in trades if t.get("status") == "closed"]
    pnls = [get_pnl(t) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    net = sum(pnls)
    wr = (len(wins) / len(closed) * 100) if closed else 0.0

    sub(f"{label} Summary")
    print(f"  total:     {total}")
    print(f"  open:      {len(open_t)}")
    print(f"  closed:    {len(closed)}")
    print(f"  wins:      {len(wins)}")
    print(f"  losses:    {len(losses)}")
    print(f"  win_rate:  {wr:.1f}%")
    print(f"  net_pnl:   {fmt(net)} toman")
    if pnls:
        print(f"  avg_pnl:   {fmt(net / len(pnls))} toman")
        print(f"  best:      {fmt(max(pnls))} toman")
        print(f"  worst:     {fmt(min(pnls))} toman")

    return {
        "total": total,
        "open": len(open_t),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": wr,
        "net": net,
        "pnls": pnls,
    }


def by_signal(trades):
    res = {}
    for t in trades:
        if t.get("status") != "closed":
            continue
        st = t.get("signal_type", "UNKNOWN")
        res.setdefault(st, []).append(t)
    return res


def paired_analysis(paper, shadow):
    sub("Paired Analysis (Paper vs Shadow)")

    p_by = by_signal(paper)
    s_by = by_signal(shadow)
    signals = sorted(set(p_by) | set(s_by))

    if not signals:
        print("  (no closed trades yet)")
        return

    header = f"  {'signal':<10} | {'P_n':>3} | {'P_pnl':>10} | {'S_n':>3} | {'S_pnl':>10} | verdict"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for sig in signals:
        p_tr = p_by.get(sig, [])
        s_tr = s_by.get(sig, [])
        p_pnl = sum(get_pnl(t) for t in p_tr)
        s_pnl = sum(get_pnl(t) for t in s_tr)

        if p_tr and s_tr:
            if s_pnl > p_pnl:
                verdict = "shadow_better"
            elif p_pnl > s_pnl:
                verdict = "paper_better"
            else:
                verdict = "equal"
        elif not p_tr and s_tr:
            verdict = "only_shadow"
        else:
            verdict = "only_paper"

        print(f"  {sig:<10} | {len(p_tr):>3} | {fmt(p_pnl):>10} | "
              f"{len(s_tr):>3} | {fmt(s_pnl):>10} | {verdict}")


def shadow_by_type(shadow):
    sub("Shadow by Type")
    groups = {}
    for t in shadow:
        st = t.get("shadow_type", "unknown")
        groups.setdefault(st, []).append(t)

    if not groups:
        print("  (no shadow trades)")
        return

    print(f"  {'type':<14} | {'total':>5} | {'open':>4} | {'closed':>6} | "
          f"{'W/L':>6} | {'WR':>5} | {'net':>10}")
    print("  " + "-" * 70)

    for st, tr in groups.items():
        open_t = [t for t in tr if t.get("status") == "open"]
        closed = [t for t in tr if t.get("status") == "closed"]
        net = sum(get_pnl(t) for t in closed)
        wins = sum(1 for t in closed if get_pnl(t) > 0)
        losses = len(closed) - wins
        wr = (wins / len(closed) * 100) if closed else 0
        print(f"  {st:<14} | {len(tr):>5} | {len(open_t):>4} | {len(closed):>6} | "
              f"{wins}/{losses:<4} | {wr:>4.0f}% | {fmt(net):>10}")


def veto_analysis(shadow):
    sub("Veto Analysis")
    vetoes = [t for t in shadow if t.get("shadow_type") == "veto"]
    if not vetoes:
        print("  (no veto shadows)")
        return

    closed = [t for t in vetoes if t.get("status") == "closed"]
    print(f"  total vetoes:  {len(vetoes)}")
    print(f"  open:          {len(vetoes) - len(closed)}")
    print(f"  closed:        {len(closed)}")

    if not closed:
        print("  (waiting for close)")
        return

    good = [t for t in closed if get_pnl(t) < 0]
    bad  = [t for t in closed if get_pnl(t) > 0]

    saved  = sum(-get_pnl(t) for t in good)
    missed = sum(get_pnl(t) for t in bad)

    print(f"  good_vetoes (would_have_lost):  {len(good)}")
    print(f"  bad_vetoes  (would_have_won):   {len(bad)}")
    print(f"  saved_toman:                    {fmt(saved)}")
    print(f"  missed_toman:                   {fmt(missed)}")
    print(f"  net_veto_impact:                {fmt(saved - missed)}")


def iran_stats(iran):
    sub("Iran News Stats")
    stats = iran.get("stats", {})
    if not stats:
        print("  (no stats)")
        return
    for k, v in stats.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk:<20}: {vv}")
        else:
            print(f"  {k:<25}: {v}")


def global_stats(gn):
    sub("Global News Stats")
    items = gn.get("items") or gn.get("news") or []
    pos_words = {"surge", "rally", "bull", "gain", "rise", "adopt",
                 "approve", "etf", "inflow", "partnership"}
    neg_words = {"crash", "drop", "bear", "fall", "ban", "hack",
                 "lawsuit", "outflow", "sec", "fraud"}

    pos = neg = 0
    for it in items:
        title = (it.get("title") or "").lower()
        pos += sum(1 for w in pos_words if w in title)
        neg += sum(1 for w in neg_words if w in title)

    print(f"  items:     {len(items)}")
    print(f"  positive:  {pos}")
    print(f"  negative:  {neg}")
    if pos > neg * 2:
        print("  sentiment: BULLISH (global veto on SELL)")
    elif neg > pos * 2:
        print("  sentiment: BEARISH (global veto on BUY)")
    else:
        print("  sentiment: NEUTRAL")


def recommendations(p_stats, s_stats, paper, shadow):
    sub("Recommendations")
    recs = []

    if p_stats["closed"] >= 4:
        wr = p_stats["win_rate"]
        if wr < 30:
            recs.append(f"[!] Paper Win Rate low ({wr:.0f}%)")
        elif wr < 50:
            recs.append(f"[~] Paper Win Rate medium ({wr:.0f}%)")
        else:
            recs.append(f"[OK] Paper Win Rate good ({wr:.0f}%)")

    if p_stats["net"] < 0:
        recs.append(f"[!] Paper Net negative ({fmt(p_stats['net'])})")
    elif p_stats["net"] > 0:
        recs.append(f"[OK] Paper Net positive ({fmt(p_stats['net'])})")

    p_by = by_signal(paper)
    for sig, tr in p_by.items():
        pnl = sum(get_pnl(t) for t in tr)
        if pnl < 0 and len(tr) >= 2:
            recs.append(f"[!] signal {sig} losing in Paper ({fmt(pnl)}) x{len(tr)}")

    if p_stats["open"] >= 2:
        recs.append(f"[i] {p_stats['open']} open Paper positions")

    if s_stats["open"] > 5:
        recs.append(f"[i] {s_stats['open']} open Shadow positions")

    p_by_sig = by_signal(paper)
    s_by_sig = by_signal(shadow)
    for sig in set(p_by_sig) & set(s_by_sig):
        p_pnl = sum(get_pnl(t) for t in p_by_sig[sig])
        s_pnl = sum(get_pnl(t) for t in s_by_sig[sig])
        if s_pnl > p_pnl and s_pnl > 0:
            recs.append(f"[?] signal {sig}: shadow better (S={fmt(s_pnl)} vs P={fmt(p_pnl)})")

    if not recs:
        recs.append("[OK] normal")

    for r in recs:
        print(f"  {r}")


def main():
    print()
    print("=" * 62)
    print(f"  ANALYZE 6 - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 62)

    paper  = load_json(F_PAPER, [])
    shadow = load_json(F_SHADOW, [])
    iran   = load_json(F_IRAN, {})
    global_news = load_json(F_GLOBAL, {})

    p_stats = summarize(paper,  "Paper Trades")
    s_stats = summarize(shadow, "Shadow Trades")

    paired_analysis(paper, shadow)
    shadow_by_type(shadow)
    veto_analysis(shadow)
    iran_stats(iran)
    global_stats(global_news)
    recommendations(p_stats, s_stats, paper, shadow)

    print()
    print("=" * 62)
    print("  END")
    print("=" * 62)


if __name__ == "__main__":
    main()
