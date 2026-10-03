#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze10.py - تحلیل جامع Paper + Shadow + Iran News
----------------------------------------------------
تغییرات نسبت به analyze9:
  - FIX 1: get_pnl — حذف شرط != 0 (باگ break-even)
  - FIX 2: parse_time — فقط ISO کامل، نه date تنها
  - FIX 3: Cohort by code_version
  - FIX 4: utcnow() → now()
  - FIX 5: ANALYZE 10 + output filename
"""

import json
import requests
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent
F_PAPER  = BASE_DIR / "paper_trades.json"
F_SHADOW = BASE_DIR / "shadow_trades.json"
F_IRAN   = BASE_DIR / "iran_news_data.json"
F_GLOBAL = BASE_DIR / "news_history.json"
F_BTC    = BASE_DIR / "btc_history.json"

WALLEX_API = "https://api.wallex.ir"
SYMBOL = "BTCTMN"
TOTAL_COST_PCT = 0.6  # fee+slip


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


# ============================================================
# FIX 1: get_pnl — حذف شرط != 0
# ============================================================
# چرا: trade با سود خالص صفر (break-even) قبلاً رد میشد
# و به اشتباه gross_pnl برمیگشت.
def get_pnl(t):
    """اولویت: net_pnl جدید → profit_net_toman قدیم → gross_pnl نهایی"""
    for key in ("net_pnl", "profit_net_toman"):
        v = t.get(key)
        if v is not None:
            return fnum(v)
    for key in ("gross_pnl", "profit_toman"):
        v = t.get(key)
        if v is not None:
            return fnum(v)
    return 0.0


def get_current_price():
    """قیمت لحظه‌ای BTC/TMN از والکس، با fallback به btc_history"""
    try:
        r = requests.get(f"{WALLEX_API}/v1/markets", timeout=15)
        if r.status_code == 200:
            data = r.json()
            last = data.get("result", {}).get("symbols", {}).get(SYMBOL, {}).get("stats", {}).get("lastPrice")
            if last:
                p = float(last)
                if p > 1_000_000_000:  # sanity check
                    return p, "wallex_live"
    except Exception as e:
        print(f"  [WARN] Wallex API error: {e}")

    # fallback
    hist = load_json(F_BTC, [])
    if hist:
        try:
            last = hist[-1]
            if isinstance(last, list) and len(last) >= 2:
                return float(last[1]), "btc_history_last"
        except Exception:
            pass
    return None, "none"


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
        "total": total, "open": len(open_t), "closed": len(closed),
        "wins": len(wins), "losses": len(losses),
        "win_rate": wr, "net": net, "pnls": pnls,
    }


def unrealized_pnl(trades, current_price, label):
    """PnL تحقق‌نیافته برای پوزیشن‌های باز"""
    sub(f"{label} - Unrealized PnL (current_price={fmt(current_price)})")

    if current_price is None:
        print("  (no current price available)")
        return 0.0

    open_t = [t for t in trades if t.get("status") == "open"]
    if not open_t:
        print("  (no open positions)")
        return 0.0

    total_unrealized = 0.0
    print(f"  {'id':<22} | {'side':<4} | {'entry':>14} | {'current':>14} | {'pnl_pct':>8} | {'pnl':>10}")
    print("  " + "-" * 90)

    for t in open_t:
        tid = t.get("id") or "?"
        if isinstance(tid, str) and len(tid) > 22:
            tid = tid[:20] + ".."
        side = (t.get("side") or "?").upper()
        entry = fnum(t.get("entry_price"))
        amount = fnum(t.get("amount_toman"))
        if entry <= 0:
            continue

        if side == "BUY":
            pnl_pct = (current_price - entry) / entry * 100
        else:  # SELL
            pnl_pct = (entry - current_price) / entry * 100

        gross = amount * pnl_pct / 100
        net = gross - amount * TOTAL_COST_PCT / 100
        total_unrealized += net

        print(f"  {tid:<22} | {side:<4} | {fmt(entry,0):>14} | {fmt(current_price,0):>14} | "
              f"{pnl_pct:>+7.2f}% | {fmt(net):>10}")

    print()
    print(f"  TOTAL unrealized: {fmt(total_unrealized)} toman")
    return total_unrealized


def by_signal(trades):
    res = {}
    for t in trades:
        if t.get("status") != "closed":
            continue
        st = t.get("signal_type", "UNKNOWN")
        res.setdefault(st, []).append(t)
    return res


def paired_analysis(paper, shadow):
    sub("Paired Analysis (Paper vs Shadow) - by signal_type")

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


# ============================================================
# FIX 2: parse_time — فقط ISO کامل، نه date تنها
# ============================================================
# چرا: date تنها ("2026-10-02") ساعت رو 00:00 می‌کرد
# و paired_by_time رو خراب می‌کرد.
def parse_time(t):
    """فقط entry_time یا time که ISO کامل باشن (>10 کاراکتر)"""
    for key in ("entry_time", "time"):
        v = t.get(key)
        if v and len(str(v)) > 10:
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
    return None


def paired_by_time(paper, shadow, window_minutes=30):
    """مقایسه Paper و Shadow که در بازه‌ی زمانی نزدیک باز شدن"""
    sub(f"Paired by Time (window ±{window_minutes} min)")

    if not paper or not shadow:
        print("  (missing data)")
        return

    p_closed = [t for t in paper if t.get("status") == "closed"]
    s_closed = [t for t in shadow if t.get("status") == "closed"]

    if not p_closed or not s_closed:
        print(f"  paper_closed={len(p_closed)} | shadow_closed={len(s_closed)}")
        print("  (need both sides closed to compare)")
        return

    # شمارش tradeهای بدون زمان معتبر
    p_no_time = sum(1 for t in p_closed if not parse_time(t))
    s_no_time = sum(1 for t in s_closed if not parse_time(t))
    if p_no_time or s_no_time:
        print(f"  [i] skipped (no valid entry_time): paper={p_no_time}, shadow={s_no_time}")

    pairs = []
    for p in p_closed:
        pt = parse_time(p)
        if not pt:
            continue
        for s in s_closed:
            st = parse_time(s)
            if not st:
                continue
            diff_min = abs((pt - st).total_seconds() / 60)
            if diff_min <= window_minutes:
                pairs.append((p, s, diff_min))

    if not pairs:
        print(f"  (no matching pairs found within ±{window_minutes} min)")
        print(f"  paper_closed={len(p_closed)} | shadow_closed={len(s_closed)}")
        return

    print(f"  Found {len(pairs)} paired trade(s):")
    print(f"  {'diff_min':>8} | {'signal':<10} | {'side':<4} | {'P_pnl':>10} | {'S_pnl':>10} | winner")
    print("  " + "-" * 70)

    for p, s, dm in pairs:
        sig = p.get("signal_type") or s.get("signal_type") or "?"
        side = (p.get("side") or s.get("side") or "?").upper()
        p_pnl = get_pnl(p)
        s_pnl = get_pnl(s)
        winner = "shadow" if s_pnl > p_pnl else ("paper" if p_pnl > s_pnl else "tie")
        print(f"  {dm:>8.1f} | {sig:<10} | {side:<4} | {fmt(p_pnl):>10} | {fmt(s_pnl):>10} | {winner}")


def top_trade_detail(paper, shadow):
    sub("TOP Trades - Detail")

    p_top = [t for t in paper if t.get("signal_type") == "TOP" and t.get("status") == "closed"]
    s_top = [t for t in shadow if t.get("signal_type") == "TOP" and t.get("status") == "closed"]

    print(f"  Paper TOP closed:  {len(p_top)}")
    print(f"  Shadow TOP closed: {len(s_top)}")

    if p_top:
        print()
        print("  --- Paper TOP (closed) ---")
        print(f"  {'entry':>14} | {'exit_reason':<12} | {'rsi':>6} | {'chg6h':>7} | {'pnl':>8}")
        print("  " + "-" * 65)
        for t in p_top:
            entry = fnum(t.get("entry_price"))
            reason = t.get("exit_reason", "?")
            rsi = t.get("rsi_at_entry")
            chg = t.get("btc_change_6h_at_entry")
            pnl = get_pnl(t)
            print(f"  {fmt(entry,0):>14} | {reason:<12} | "
                  f"{fmt(rsi,2):>6} | {fmt(chg,2):>7} | {fmt(pnl):>8}")

    if s_top:
        print()
        print("  --- Shadow TOP (closed) ---")
        print(f"  {'entry':>14} | {'exit_reason':<12} | {'rsi':>6} | {'chg6h':>7} | {'pnl':>8}")
        print("  " + "-" * 65)
        for t in s_top:
            entry = fnum(t.get("entry_price"))
            reason = t.get("exit_reason", "?")
            rsi = t.get("rsi_at_entry")
            chg = t.get("btc_change_6h_at_entry")
            pnl = get_pnl(t)
            print(f"  {fmt(entry,0):>14} | {reason:<12} | "
                  f"{fmt(rsi,2):>6} | {fmt(chg,2):>7} | {fmt(pnl):>8}")


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


# ============================================================
# FIX 3: Cohort by code_version (جدید)
# ============================================================
def cohort_by_version(trades, label):
    sub(f"{label} - Cohort by code_version")

    if not trades:
        print("  (no trades)")
        return

    cohorts = {}
    for t in trades:
        meta = t.get("metadata") or {}
        ver = meta.get("code_version")
        if not ver:
            # fallback: شاید فیلد مستقیم باشه
            ver = t.get("code_version") or "unknown"
        cohorts.setdefault(ver, []).append(t)

    if not cohorts:
        print("  (no cohort data)")
        return

    print(f"  {'version':<16} | {'total':>5} | {'open':>4} | {'closed':>6} | "
          f"{'W/L':>6} | {'WR':>5} | {'net':>10}")
    print("  " + "-" * 75)

    for ver in sorted(cohorts.keys()):
        tr = cohorts[ver]
        open_t = [t for t in tr if t.get("status") == "open"]
        closed = [t for t in tr if t.get("status") == "closed"]
        net = sum(get_pnl(t) for t in closed)
        wins = sum(1 for t in closed if get_pnl(t) > 0)
        losses = len(closed) - wins
        wr = (wins / len(closed) * 100) if closed else 0
        wr_str = f"{wr:.0f}%" if closed else "-"
        print(f"  {ver:<16} | {len(tr):>5} | {len(open_t):>4} | {len(closed):>6} | "
              f"{wins}/{losses:<4} | {wr_str:>5} | {fmt(net):>10}")


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
    if not isinstance(gn, list) or not gn:
        print("  (no global news data)")
        return

    latest = gn[-1]
    pos = int(latest.get("pos", 0) or 0)
    neg = int(latest.get("neg", 0) or 0)
    sentiment = latest.get("sentiment", "neutral")

    print(f"  snapshots:     {len(gn)}")
    print(f"  latest_time:   {latest.get('time', 'N/A')}")
    print(f"  pos:           {pos}")
    print(f"  neg:           {neg}")
    print(f"  sentiment:     {sentiment}")

    if pos > neg * 2:
        print(f"  veto_status:   BULLISH (would veto SELL)")
    elif neg > pos * 2:
        print(f"  veto_status:   BEARISH (would veto BUY)")
    else:
        print(f"  veto_status:   NEUTRAL (no veto)")

    last5 = gn[-5:] if len(gn) >= 5 else gn
    print()
    print(f"  Trend (last {len(last5)} snapshots):")
    print(f"    {'time':<20} | {'pos':>4} | {'neg':>4} | sentiment")
    print(f"    {'-'*20}-+-{'-'*4}-+-{'-'*4}-+-{'-'*12}")
    for snap in last5:
        t = (snap.get("time", "") or "")[:19]
        p = int(snap.get("pos", 0) or 0)
        n = int(snap.get("neg", 0) or 0)
        s = snap.get("sentiment", "?")
        print(f"    {t:<20} | {p:>4} | {n:>4} | {s}")


def recommendations(p_stats, s_stats, paper, shadow, unreal_p, unreal_s):
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

    if unreal_p < 0:
        recs.append(f"[!] Paper Unrealized negative ({fmt(unreal_p)})")
    elif unreal_p > 0:
        recs.append(f"[OK] Paper Unrealized positive ({fmt(unreal_p)})")

    if unreal_s < 0:
        recs.append(f"[!] Shadow Unrealized negative ({fmt(unreal_s)})")
    elif unreal_s > 0:
        recs.append(f"[OK] Shadow Unrealized positive ({fmt(unreal_s)})")

    p_by = by_signal(paper)
    for sig, tr in p_by.items():
        pnl = sum(get_pnl(t) for t in tr)
        if pnl < 0 and len(tr) >= 2:
            recs.append(f"[!] signal {sig} losing in Paper ({fmt(pnl)}) x{len(tr)}")

    if p_stats["open"] >= 2:
        recs.append(f"[i] {p_stats['open']} open Paper positions")

    if s_stats["open"] > 5:
        recs.append(f"[i] {s_stats['open']} open Shadow positions")

    if not recs:
        recs.append("[OK] normal")

    for r in recs:
        print(f"  {r}")


def main():
    print()
    print("=" * 62)
    # FIX 4: utcnow() → now()
    print(f"  ANALYZE 10 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 62)

    paper  = load_json(F_PAPER, [])
    shadow = load_json(F_SHADOW, [])
    iran   = load_json(F_IRAN, {})
    global_news = load_json(F_GLOBAL, [])

    current_price, price_src = get_current_price()
    print(f"  Current BTC/TMN: {fmt(current_price,0)} (source={price_src})")

    p_stats = summarize(paper,  "Paper Trades")
    s_stats = summarize(shadow, "Shadow Trades")

    unreal_p = unrealized_pnl(paper, current_price, "Paper")
    unreal_s = unrealized_pnl(shadow, current_price, "Shadow")

    # FIX 3: cohort by version
    cohort_by_version(paper, "Paper")
    cohort_by_version(shadow, "Shadow")

    paired_analysis(paper, shadow)
    paired_by_time(paper, shadow, window_minutes=30)
    top_trade_detail(paper, shadow)
    shadow_by_type(shadow)
    iran_stats(iran)
    global_stats(global_news)
    recommendations(p_stats, s_stats, paper, shadow, unreal_p, unreal_s)

    print()
    print("=" * 62)
    print("  END")
    print("=" * 62)


if __name__ == "__main__":
    main()
