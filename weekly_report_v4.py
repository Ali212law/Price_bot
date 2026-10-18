#!/usr/bin/env python3
# weekly_report_v4.py — v4.1 | 2026-10-18 | AI سوم (هوشا)
# کوهورت 33/34 = CONTROL (paper, active) | کوهورت 35 = OFFICIAL M2
# Shadow Lab v5.3 (ساختار dict) + قرنطینه H6 + گیت آماری 3.2 (Wilson 95%)
import json, math
from datetime import datetime, timezone
from collections import Counter

F_PAPER34  = "paper_trades.json"
F_PAPER35  = "paper_trades35.json"
F_SHADOW34 = "shadow_trades.json"
F_LAB35    = "shadow_lab_trades.json"
F_ANCHOR34 = "time_anchor.json"
F_ANCHOR35 = "time_anchor35.json"
F_QUAR     = "quarantine35.json"

GATE_MIN_N    = 30
GATE_MIN_DAYS = 21
BREAKEVEN_WR  = 0.4333
Z95           = 1.96
STALE_MIN     = 90
EXP_REVIEW    = "2026-11-18"

BUILTIN_QUAR = {"H6": {"status": "quarantined", "date": "2026-10-18",
                       "decision": "D-2026-10-18-02",
                       "reason": "OOS45 Net=-14.1%; reactivation undocumented"}}

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

def sig_of(r):
    return str(r.get("signal_type", "") or "").upper()

def num_of(r, keys):
    for k in keys:
        if k in r:
            try:
                return float(r[k])
            except Exception:
                pass
    return None

def net_toman_of(r):
    return num_of(r, ("profit_net_toman", "net_pnl", "profit_net"))

def net_pct_of(r):
    return num_of(r, ("profit_net_pct", "net_pnl_pct"))

def entry_ts(r):
    return parse_ts(r.get("entry_time") or r.get("time"))

def is_win(r):
    v = net_toman_of(r)
    if v is None:
        v = net_pct_of(r)
    return (v > 0) if v is not None else None

def wilson_lower(k, n, z=Z95):
    if not n:
        return None
    p = k / float(n)
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return center - half

def indep_days(recs):
    ds = set()
    for r in recs:
        ts = entry_ts(r)
        if ts:
            ds.add(ts.strftime("%Y-%m-%d"))
    return len(ds)

def is_tagged(r):
    for k in ("administrative_close", "orphaned_legacy", "admin_close"):
        if k in r:
            return True
    tags = r.get("tags") or r.get("tag")
    if isinstance(tags, str):
        return any(t in tags for t in ("administrative_close", "orphaned_legacy"))
    if isinstance(tags, list):
        return any(str(t) in ("administrative_close", "orphaned_legacy") for t in tags)
    return False

def quar_map():
    merged = dict(BUILTIN_QUAR)
    q = load(F_QUAR)
    if isinstance(q, dict):
        merged.update(q)
    return merged

def quar_status(name, quar):
    if name in quar:
        v = quar[name]
        return str(v.get("status", "") if isinstance(v, dict) else (v or "")).lower()
    for kk, vv in quar.items():
        if str(name).startswith(str(kk)):
            return str(vv.get("status", "") if isinstance(vv, dict) else (vv or "")).lower()
    return ""

def anchor_block(title, fn):
    print("\n--- ANCHOR %s (%s) ---" % (title, fn))
    a = load(fn)
    if not isinstance(a, dict):
        print("MISSING or unreadable")
        return None
    print(json.dumps(a, ensure_ascii=False))
    ts = parse_ts(a.get("last_run_utc") or a.get("last_run"))
    lock = str(a.get("lock_date") or "")[:10] or None
    if ts is None:
        print("timestamp: UNPARSEABLE")
        return lock
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    flag = "  !! STALE > %d min" % STALE_MIN if age > STALE_MIN else ""
    print("age: %.0f min%s" % (age, flag))
    if age > STALE_MIN:
        print("   (اگر در ترموس اجرا شده: اول git pull بزن؛ وگرنه وضعیت ذخیره را چک کن)")
    return lock

def stats_line(closed):
    wins = [w for w in (is_win(r) for r in closed) if w is not None]
    wr = (sum(1 for w in wins if w) / float(len(wins))) if wins else None
    nets = [v for v in (net_toman_of(r) for r in closed) if v is not None]
    pcts = [v for v in (net_pct_of(r) for r in closed) if v is not None]
    return (len(closed), wr,
            sum(nets) if nets else 0.0,
            (sum(pcts) / len(pcts)) if pcts else None)

def paper_block(title, recs, official_m2=False, lock_date=None):
    print("\n--- %s ---" % title)
    if not isinstance(recs, list):
        print("MISSING or unreadable")
        return
    print("records: %d" % len(recs))
    if not recs:
        print("EMPTY")
        if official_m2:
            print(">> OFFICIAL M2 COUNTER: DIP closed 0/%d" % GATE_MIN_N)
        return
    open_tr = [r for r in recs if status_of(r) == "open"]
    closed  = [r for r in recs if status_of(r) == "closed"]
    tagged  = [r for r in closed if is_tagged(r)]
    clean   = [r for r in closed if not is_tagged(r)]
    st = Counter(status_of(r) or "?" for r in recs)
    print("status distribution: %s" % dict(st))
    n, wr, net, mean_pct = stats_line(clean)
    if n:
        print("closed(clean): %d | WR: %s | Net: %+.0f Toman | mean net%%: %s | indep-days: %d"
              % (n, ("%.1f%%" % (wr * 100)) if wr is not None else "?", net,
                 ("%.2f%%" % mean_pct) if mean_pct is not None else "?",
                 indep_days(clean)))
    else:
        print("closed(clean): 0")
    if tagged:
        n2, wr2, net2, _mp = stats_line(tagged)
        print("closed(tagged admin/legacy): %d | WR: %s | Net: %+.0f | جدا از آمار عادی (D.1)"
              % (n2, ("%.1f%%" % (wr2 * 100)) if wr2 is not None else "?", net2))
    now = datetime.now(timezone.utc)
    if open_tr:
        print("OPEN trades: %d" % len(open_tr))
        for r in open_tr:
            ts = entry_ts(r)
            hrs = ((now - ts).total_seconds() / 3600.0) if ts else None
            print("  open: entry=%s | RSI=%s | amount=%s | open-hours=%s"
                  % (r.get("entry_time") or r.get("time"), r.get("rsi_at_entry"),
                     r.get("amount_toman"), ("%.1f" % hrs) if hrs is not None else "?"))
    else:
        print("OPEN trades: 0")
    if official_m2:
        dips_closed = [r for r in clean if sig_of(r) == "DIP"]
        k = len(dips_closed)
        wins = [w for w in (is_win(r) for r in dips_closed) if w is not None]
        kw = sum(1 for w in wins if w)
        lo = wilson_lower(kw, k) if k else None
        print(">> OFFICIAL M2 COUNTER: DIP closed %d/%d (wins=%d)" % (k, GATE_MIN_N, kw))
        days = None
        if lock_date:
            try:
                d0 = datetime.strptime(lock_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days = (datetime.now(timezone.utc) - d0).days
            except Exception:
                pass
        c_n  = k >= GATE_MIN_N
        c_d  = (days is not None and days >= GATE_MIN_DAYS)
        c_ci = (lo is not None and lo > BREAKEVEN_WR)
        gate = "PASS" if (c_n and c_d and c_ci) else "NOT YET"
        print(">> GATE 3.2 (LOCKED): n>=30:%s | days>=21:%s(%s) | WilsonLo95=%s>43.33%%:%s => %s"
              % (c_n, c_d, days if days is not None else "?",
                 ("%.1f%%" % (lo * 100)) if lo is not None else "n/a", c_ci, gate))
        print("   (جدول توان و پیشنهاد لایه‌بندی: DECISIONS.md پیوست A)")

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

def lab_block(lab, quar):
    print("\n--- SHADOW LAB v5.3 (%s) ---" % F_LAB35)
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
        items = sorted(accs.items())
    elif isinstance(accs, list):
        items = [(str(i), a) for i, a in enumerate(accs)]
    else:
        print("accounts: UNEXPECTED type %s" % type(accs).__name__)
        return
    print("strategies: %d" % len(items))
    print("%-16s | %6s | %6s | %7s | %9s | %s"
          % ("strategy", "trades", "closed", "WR%", "Net%", "status"))
    formal_pool = []
    all_trades = []
    for name, acc in items:
        trs = lab_trades_of(acc)
        all_trades.extend(trs)
        closed = [r for r in trs if status_of(r) == "closed"]
        wins = [w for w in (is_win(r) for r in closed) if w is not None]
        wr = (sum(1 for w in wins if w) / float(len(wins))) if wins else None
        pcts = [v for v in (net_pct_of(r) for r in closed) if v is not None]
        netp = sum(pcts) if pcts else None
        q = quar_status(str(name), quar)
        if q == "quarantined":
            tag = "QUARANTINED"
        elif str(name).startswith(("H5", "H8", "H9")):
            tag = "EXPERIMENTAL(rev %s)" % EXP_REVIEW
        else:
            tag = "ACTIVE"
            formal_pool.append(str(name))
        print("%-16s | %6d | %6d | %7s | %9s | %s"
              % (str(name)[:16], len(trs), len(closed),
                 ("%.1f" % (wr * 100)) if wr is not None else "-",
                 ("%+.2f" % netp) if netp is not None else "-", tag))
    print("formal comparison pool: %s" % (", ".join(formal_pool) if formal_pool else "EMPTY"))
    groups = Counter()
    for r in all_trades:
        ts = entry_ts(r)
        key = (ts.strftime("%Y-%m-%dT%H:%M") if ts else "?", r.get("entry_price"))
        groups[key] += 1
    common = [(gk, c) for gk, c in groups.items() if c > 1]
    print("entry groups shared by 2+ strategies (paired base): %d" % len(common))
    for (tkey, price), cnt in common[:5]:
        print("  %s @ %s -> %d strategies" % (tkey, price, cnt))

def main():
    now = datetime.now(timezone.utc)
    print("=" * 66)
    print("WEEKLY REPORT v4.1 — %s UTC" % now.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 66)
    quar = quar_map()
    lock35 = anchor_block("35 (M2)", F_ANCHOR35)
    anchor_block("33/34 (CONTROL)", F_ANCHOR34)

    p34 = load(F_PAPER34)
    p35 = load(F_PAPER35)
    s34 = load(F_SHADOW34)
    lab = load(F_LAB35)

    paper_block("COHORT 33/34 PAPER — CONTROL (paper, active) — judged only as control", p34)
    paper_block("COHORT 35 PAPER M2 — OFFICIAL", p35, official_m2=True, lock_date=lock35)
    paper_block("SHADOW 33/34 (shadow_trades.json) — reference only", s34)
    lab_block(lab, quar)

    print("\nNOTES:")
    print("- M2 counter: ONLY real closed DIP trades of Paper35 (locked definition).")
    print("- Shadow trades are NEVER counted toward the M2 counter.")
    print("- CONTROL cohort is never mixed into M2 stats (D-2026-10-18-04).")
    print("- indep-days = unique UTC entry dates of closed trades (D-2026-10-18-07).")
    print("- Wilson 95% lower bound per GATE 3.2; power table: DECISIONS.md annex A.")
    print("- Quarantine: builtin H6 + optional %s; quarantined = out of formal pool." % F_QUAR)

if __name__ == "__main__":
    main()
