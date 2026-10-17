#!/usr/bin/env python3
"""
full_export.py — خروجی جامع داده‌ها برای بررسی خارجی (read-only)
"""
import json
from collections import Counter, defaultdict
from datetime import datetime

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
BTC_HISTORY_FILE = "btc_history.json"
TIME_ANCHOR_FILE = "time_anchor.json"
OUTPUT = "EXPORT.txt"
CODE_VERSIONS = ("paper_trade33", "paper_trade34")


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception:
        return None


def sec(title):
    return "\n" + "=" * 70 + "\n" + title + "\n" + "=" * 70 + "\n"


def main():
    out = []
    anchor = load(TIME_ANCHOR_FILE) or {}
    out.append(sec("TIME ANCHOR"))
    out.append(json.dumps(anchor, indent=2, ensure_ascii=False))

    p = load(PAPER_FILE) or []
    s = load(SHADOW_FILE) or []
    b = load(BTC_HISTORY_FILE) or []

    out.append(sec("DATASET OVERVIEW"))
    out.append(f"paper_trades: {len(p)}")
    out.append(f"shadow_trades: {len(s)}")
    out.append(f"btc_history: {len(b)}")
    if b:
        try:
            span_h = (datetime.fromisoformat(b[-1][0]) - datetime.fromisoformat(b[0][0])).total_seconds() / 3600
            out.append(f"btc_history span: {span_h:.1f}h")
        except Exception:
            pass
        out.append(f"btc_history oldest: {b[0][0]}")
        out.append(f"btc_history latest: {b[-1][0]}")

    out.append(sec("SECTION 1 — PAPER TRADES (full)"))
    for t in sorted(p, key=lambda x: x.get("entry_time", "")):
        m = t.get("metadata") or {}
        et = (t.get("entry_time") or "?")[:19]
        xt = (t.get("exit_time") or "?")[:19]
        entry = t.get("entry_price", 0) / 1e9
        exit_p = (t.get("exit_price") or 0) / 1e9
        rsi = m.get("rsi_value")
        chg6 = m.get("btc_change_6h_avg")
        reg = m.get("regime_avg", "?")
        net = t.get("profit_net_toman") or 0
        out.append(
            f"{et} | {xt} | {t.get('side','?')} | {t.get('signal_type','?')} | "
            f"{t.get('status','?')} | entry={entry:.3f}B | exit={exit_p:.3f}B | "
            f"reason={t.get('exit_reason','-')} | rsi={rsi} | chg6h={chg6} | "
            f"reg={reg} | net={net:+.0f}"
        )

    out.append(sec("SECTION 2 — SHADOW TRADES (by type & status)"))
    c = Counter((t.get("shadow_type", "?"), t.get("status", "?")) for t in s)
    for (typ, st), n in sorted(c.items()):
        out.append(f"  {typ:40s} | {st:8s} | {n}")

    out.append(sec("SECTION 3 — STOP CONDITION"))
    all_t = [t for t in p + s if (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    dips = [t for t in all_t if t.get("signal_type") == "DIP"]
    dips_closed = [t for t in dips if t.get("status") == "closed"]
    by_regime = defaultdict(int)
    for t in dips_closed:
        reg = (t.get("metadata") or {}).get("regime_avg", "unknown")
        by_regime[reg] += 1
    out.append(f"DIP total: {len(dips)}")
    out.append(f"DIP closed: {len(dips_closed)}/100")
    out.append(f"Regimes: {dict(by_regime)}")
    out.append(f"Time anchor last_run: {anchor.get('last_run_utc', '?')}")

    out.append(sec("SECTION 4 — SIGNAL DISTRIBUTION (cohort 33/34)"))
    sig_c = Counter(t.get("signal_type", "?") for t in all_t)
    for sig in ["DIP", "TOP", "MOMENTUM", "VERY_STRONG", "STRONG", "MEDIUM"]:
        n = sig_c.get(sig, 0)
        mark = "YES" if n > 0 else "NO "
        out.append(f"  [{mark}] {sig:15s} {n}")

    out.append(sec("SECTION 5 — REGIME LOG BY DAY"))
    by_day = defaultdict(list)
    for t in all_t:
        d = (t.get("entry_time") or "?")[:10]
        m = t.get("metadata") or {}
        by_day[d].append({
            "reg": m.get("regime_avg", "?"),
            "chg24": m.get("btc_change_24h_avg"),
            "chg6": m.get("btc_change_6h_avg"),
        })
    for d in sorted(by_day.keys()):
        trades = by_day[d]
        regs = Counter(x["reg"] for x in trades)
        chg24_vals = [x["chg24"] for x in trades if x["chg24"] is not None]
        chg6_vals = [x["chg6"] for x in trades if x["chg6"] is not None]
        chg24_avg = round(sum(chg24_vals)/len(chg24_vals), 4) if chg24_vals else None
        chg6_avg = round(sum(chg6_vals)/len(chg6_vals), 4) if chg6_vals else None
        out.append(f"  {d}: n={len(trades):3d} | regimes={dict(regs)} | chg24_avg={chg24_avg} | chg6_avg={chg6_avg}")

    out.append(sec("SECTION 6 — PAPER BY SIGNAL (closed only)"))
    paper_closed = [t for t in p if t.get("status") == "closed"]
    g = defaultdict(lambda: {"n": 0, "w": 0, "net": 0})
    for t in paper_closed:
        sig = t.get("signal_type", "?")
        net = t.get("profit_net_toman") or 0
        g[sig]["n"] += 1
        g[sig]["net"] += net
        if net > 0:
            g[sig]["w"] += 1
    for sig in sorted(g.keys()):
        d = g[sig]
        wr = d["w"] / d["n"] * 100 if d["n"] else 0
        out.append(f"  {sig:15s} n={d['n']:3d} | WR={wr:5.1f}% | net={d['net']:+10.0f}")

    out.append(sec("SECTION 7 — CUMULATIVE PnL (paper closed)"))
    cum = 0
    for t in sorted(paper_closed, key=lambda x: x.get("exit_time") or x.get("entry_time", "")):
        cum += (t.get("profit_net_toman") or 0)
        xt = (t.get("exit_time") or "?")[:19]
        out.append(f"  {xt} | net={t.get('profit_net_toman',0):+10.0f} | cumulative={cum:+10.0f}")

    out.append(sec("SECTION 8 — DORMANT SIGNALS EXPLANATION"))
    out.append("MOMENTUM:     needs |chg6h| >= 2.0% - rarely in range/chop")
    out.append("VERY_STRONG:  needs RSI<30 + chg6h>=1.5% - rare")
    out.append("STRONG:       needs RSI<35 + chg6h>=1.0% - rare")
    out.append("MEDIUM:       needs RSI 30-45 + chg6h>=0.5% - skipped in fast bounces")

    text = "\n".join(out)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Exported to {OUTPUT}")
    print(f"Total lines: {len(out)}")
    print(f"File size: {len(text)} bytes")


if __name__ == "__main__":
    main()
