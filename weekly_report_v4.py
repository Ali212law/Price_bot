#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from collections import Counter

F_PAPER34  = "paper_trades.json"
F_PAPER35  = "paper_trades35.json"
F_SHADOW34 = "shadow_trades.json"
F_LAB35    = "shadow_lab_trades.json"
F_ANCHOR34 = "time_anchor.json"
F_ANCHOR35 = "time_anchor35.json"

TARGET_DIP = 100
MIN_DAYS   = 14
STALE_MIN  = 90
LEGACY_TAGS = ("administrative_close", "orphaned_legacy", "admin_close")

def load(fn):
    try:
        with open(fn, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def parse_ts(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def status_of(r):
    return str(r.get("status", "") or "").lower()

def net_of(r):
    for k in ("profit_net_toman", "net_pnl", "profit_net"):
        if k in r:
            try:
                return float(r[k])
            except Exception:
                pass
    return None

def entry_ts(r):
    return parse_ts(r.get("entry_time") or r.get("time"))

def is_tagged(r):
    if any(k in r for k in LEGACY_TAGS):
        return True
    tags = r.get("tags") or r.get("tag")
    if isinstance(tags, str):
        return any(t in tags for t in LEGACY_TAGS)
    if isinstance(tags, list):
        return any(str(t) in LEGACY_TAGS for t in tags)
    return False

def stats(closed):
    nets = [net_of(r) for r in closed]
    nets = [n for n in nets if n is not None]
    wr = (100.0 * sum(1 for n in nets if n > 0) / len(nets)) if nets else None
    return wr, (sum(nets) if nets else 0.0), len(nets)

def indep_days(recs):
    ds = set()
    for r in recs:
        ts = entry_ts(r)
        if ts:
            ds.add(ts.strftime("%Y-%m-%d"))
    return len(ds)

def anchor_block(title, fn):
    print("\n--- ANCHOR %s (%s) ---" % (title, fn))
    a = load(fn)
    if not isinstance(a, dict):
        print("MISSING or unreadable")
        return None, None
    print(json.dumps(a, ensure_ascii=False))
    ts = parse_ts(a.get("last_run_utc") or a.get("last_run"))
    lock = str(a.get("lock_date") or "")[:10] or None
    age = ((datetime.now(timezone.utc) - ts).total_seconds() / 60.0) if ts else None
    if age is None:
        print("timestamp: UNPARSEABLE")
    else:
        flag = "  !! STALE > %d min" % STALE_MIN if age > STALE_MIN else ""
        print("age: %.0f min%s" % (age, flag))
    return age, lock

def paper_block(title, recs, official_m2=False, lock_date=None):
    print("\n--- %s ---" % title)
    if recs is None or not isinstance(recs, list):
        print("MISSING or unreadable")
        return
    recs = recs
    print("records: %d" % len(recs)) if recs else print("records: 0 (EMPTY)")
    open_tr = [r for r in recs if status_of(r) == "open"]
    closed  = [r for r in recs if status_of(r) == "closed"]
    tagged  = [r for r in closed if is_tagged(r)]
    clean   = [r for r in closed if not is_tagged(r)]
    dips_closed = [r for r in clean if str(r.get("signal_type", "")).upper() == "DIP"]
    st = Counter(status_of(r) or "?" for r in recs)
    print("status distribution: %s" % dict(st))
    wr, net, n = stats(clean)
    if n:
        print("closed(clean): %d | WR: %.1f%% | Net: %+.0f Toman | indep-days(approx): %d"
              % (n, wr, net, indep_days(clean)))
    else:
        print("closed(clean): 0")
    if tagged:
        wr2, net2, n2 = stats(tagged)
        print("closed(tagged legacy/admin): %d | WR: %s | Net: %+.0f | جدا از آمار عادی (D.1)"
              % (n2, ("%.1f%%" % wr2) if wr2 is not None else "?", net2))
    if open_tr:
        print("OPEN trades: %d" % len(open_tr))
        for r in open_tr:
            ts = entry_ts(r)
            hrs = ((datetime.now(timezone.utc) - ts).total_seconds() / 3600.0) if ts else None
            print("  open: entry=%s | RSI=%s | amount=%s | open-hours=%s" % (
                r.get("entry_time") or r.get("time"), r.get("rsi_at_entry"),
                r.get("amount_toman"), ("%.1f" % hrs) if hrs is not None else "?"))
    else:
        print("OPEN trades: 0")
    if official_m2:
        print(">> OFFICIAL M2 COUNTER: DIP closed %d/%d" % (len(dips_closed), TARGET_DIP))
        days = None
        if lock_date:
            try:
                d0 = datetime.strptime(lock_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days = (datetime.now(timezone.utc) - d0).days
            except Exception:
                pass
        met_dip = len(dips_closed) >= TARGET_DIP
        met_days = (days is not None and days >= MIN_DAYS)
        print(">> stop condition (AND): DIP %s | days %s (%s) => %s" % (
            "MET" if met_dip else "not met",
            days if days is not None else "?",
            "MET" if met_days else "not met",
            "TRIGGERED" if (met_dip and met_days) else "ACTIVE"))

def lab_trades_of(acc):
    if isinstance(acc, list):
        return [x for x in acc if isinstance(x, dict)]
    if isinstance(acc, dict):
        for key in ("trades", "history", "records", "positions", "log",
                    "closed_trades", "open_trades"):
            v = acc.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        for v in acc.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return [x for x in v if isinstance(x, dict)]
    return []

def lab_block(lab):
    print("\n--- SHADOW LAB v5.3 (%s) — dict structure, defensive parse ---" % F_LAB35)
    if lab is None:
        print("MISSING or unreadable")
        return
    if not isinstance(lab, dict):
        print("UNEXPECTED type: %s — report to AI3" % type(lab).__name__)
        return
    print("last_check_utc: %s | last_live_price: %s"
          % (lab.get("last_check_utc"), lab.get("last_live_price")))
    accs = lab.get("accounts")
    if isinstance(accs, dict):
        items = list(accs.items())
    elif isinstance(accs, list):
        items = [(str(i), a) for i, a in enumerate(accs)]
    else:
        print("accounts: UNEXPECTED type %s" % type(accs).__name__)
        return
    print("strategies: %d" % len(items))
    print("%-16s | %6s | %6s | %7s | %9s" % ("strategy", "trades", "closed", "WR%", "Net(T)"))
    for name, acc in items:
        trs = lab_trades_of(acc)
        closed = [r for r in trs if status_of(r) == "closed"]
        wr, net, n = stats(closed)
        print("%-16s | %6d | %6d | %7s | %9s" % (
            str(name)[:16], len(trs), len(closed),
            ("%.1f" % wr) if wr is not None else "-",
            ("%+.0f" % net) if n else "-"))

def main():
    now = datetime.now(timezone.utc)
    print("=" * 62)
    print("WEEKLY REPORT v4 — %s UTC" % now.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 62)

    age35, lock35 = anchor_block("35 (M2)", F_ANCHOR35)
    anchor_block("33/34 (old)", F_ANCHOR34)

    p34 = load(F_PAPER34)
    p35 = load(F_PAPER35)
    s34 = load(F_SHADOW34)
    lab = load(F_LAB35)

    paper_block("COHORT 33/34 PAPER (paper_trades.json) — FROZEN; open = orphaned_legacy (D.1)", p34)
    paper_block("COHORT 35 PAPER M2 (paper_trades35.json) — OFFICIAL", p35,
                official_m2=True, lock_date=lock35)
    paper_block("SHADOW 33/34 (shadow_trades.json) — reference only", s34)
    lab_block(lab)

    print("\nNOTES:")
    print("- M2 counter counts ONLY real closed DIP trades of Paper35 (locked definition).")
    print("- indep-days is approximate (unique UTC entry dates); formal definition pending.")
    print("- Cohort 33/34 open trades can never close (workflow deleted); per D.1 they are")
    print("  listed separately and tagged records are excluded from normal stats.")
    print("- Shadow Lab trades are NEVER counted toward the M2 counter.")

if __name__ == "__main__":
    main()
