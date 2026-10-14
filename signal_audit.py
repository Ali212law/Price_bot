#!/usr/bin/env python3
"""
signal_audit.py — بررسی «چرا ۸ سیگنال خاموشن؟»
read-only: برای هر trade موجود، تمام شرایط ۱۰ سیگنال را چک می‌کند
"""
import json
from collections import Counter

PAPER_FILE = "paper_trades.json"
SHADOW_FILE = "shadow_trades.json"
CODE_VERSIONS = ("paper_trade33", "paper_trade34")

# آستانه‌ها (باید با paper_trade34 هماهنگ باشند)
RSI_OVERSOLD = 30
RSI_LOW = 35
RSI_MILD_LOW = 45
RSI_MILD_HIGH = 65
RSI_HIGH = 70
RSI_OVERBOUGHT = 75

THRESHOLD_VERY_STRONG = 1.5
THRESHOLD_STRONG = 1.0
THRESHOLD_MEDIUM = 0.5
THRESHOLD_MOMENTUM = 2.0


def load(fn):
    try:
        with open(fn) as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {fn}: {e}")
        return []


def get_metadata_vals(t):
    m = t.get("metadata") or {}
    return {
        "rsi": m.get("rsi_value"),
        "chg6h": m.get("btc_change_6h_avg"),
        "chg24h": m.get("btc_change_24h_avg"),
        "regime": m.get("regime_avg"),
        "rsi_valid": m.get("rsi_valid", True),
    }


def eligible_signals(rsi, chg6h, rsi_valid):
    """کدام سیگنال‌ها شرایط را دارند (مستقل از priority)"""
    eligible = []
    if rsi is None or chg6h is None:
        return eligible
    if not rsi_valid:
        # RSI-based سرکوب می‌شن، فقط MOMENTUM باقی
        if chg6h >= THRESHOLD_MOMENTUM:
            eligible.append("MOMENTUM_BUY")
        if chg6h <= -THRESHOLD_MOMENTUM:
            eligible.append("MOMENTUM_SELL")
        return eligible

    # BUY
    if rsi < RSI_OVERSOLD and chg6h >= THRESHOLD_VERY_STRONG:
        eligible.append("VERY_STRONG_BUY")
    if rsi < RSI_LOW and chg6h >= THRESHOLD_STRONG:
        eligible.append("STRONG_BUY")
    if rsi < RSI_MILD_LOW and chg6h >= THRESHOLD_MEDIUM:
        eligible.append("MEDIUM_BUY")
    if rsi < RSI_OVERSOLD:
        eligible.append("DIP")
    if chg6h >= THRESHOLD_MOMENTUM:
        eligible.append("MOMENTUM_BUY")

    # SELL
    if rsi > RSI_OVERBOUGHT and chg6h <= -THRESHOLD_VERY_STRONG:
        eligible.append("VERY_STRONG_SELL")
    if rsi > RSI_HIGH and chg6h <= -THRESHOLD_STRONG:
        eligible.append("STRONG_SELL")
    if rsi > RSI_MILD_HIGH and chg6h <= -THRESHOLD_MEDIUM:
        eligible.append("MEDIUM_SELL")
    if rsi > RSI_OVERBOUGHT:
        eligible.append("TOP")
    if chg6h <= -THRESHOLD_MOMENTUM:
        eligible.append("MOMENTUM_SELL")

    return eligible


def main():
    print("=" * 62)
    print("SIGNAL AUDIT — کدام سیگنال‌ها شرایطشان برقرار بوده؟")
    print("=" * 62)

    p = load(PAPER_FILE)
    s = load(SHADOW_FILE)

    # همه trade های cohort جدید
    all_trades = [t for t in p + s
                  if (t.get("metadata") or {}).get("code_version") in CODE_VERSIONS]
    print(f"\nTotal trades (cohort 33/34): {len(all_trades)}")

    # برای هر trade، شرایط چه سیگنال‌هایی برقرار بوده؟
    fired_counter = Counter()         # چیزی که واقعاً fire شد
    eligible_counter = Counter()      # چیزی که شرایطش بود
    priority_suppressed = Counter()   # شرایط بود ولی fire نشد (اولویت پایین‌تر)

    for t in all_trades:
        vals = get_metadata_vals(t)
        fired = t.get("signal_type", "?")
        side = (t.get("side") or "").lower()
        fired_key = f"{fired}_{side.upper()}" if side else fired
        fired_counter[fired_key] += 1

        elig = eligible_signals(vals["rsi"], vals["chg6h"], vals["rsi_valid"])
        for e in elig:
            eligible_counter[e] += 1
        # کدام eligibleها fire نشدند؟
        for e in elig:
            if e != fired_key and not (e == "DIP" and fired_key == "DIP"):
                priority_suppressed[e] += 1

    print(f"\n[1] Fired signals (واقعاً انتخاب شدند)")
    for k, v in fired_counter.most_common():
        print(f"  {k:25s} {v}")

    print(f"\n[2] Eligible signals (شرایط برقرار بوده)")
    for k, v in eligible_counter.most_common():
        print(f"  {k:25s} {v}")

    print(f"\n[3] Priority-suppressed (شرایط بود ولی انتخاب نشد)")
    for k, v in priority_suppressed.most_common():
        print(f"  {k:25s} {v}")

    # جمع‌بندی
    print(f"\n[4] خلاصه")
    print(f"  کل trade: {len(all_trades)}")
    unique_fired = len(fired_counter)
    unique_eligible = len(eligible_counter)
    print(f"  سیگنال‌های fired:    {unique_fired}")
    print(f"  سیگنال‌های eligible: {unique_eligible}")

    # ۱۰ سیگنال ممکن
    all_signals = ["VERY_STRONG_BUY", "STRONG_BUY", "MEDIUM_BUY", "DIP", "MOMENTUM_BUY",
                   "VERY_STRONG_SELL", "STRONG_SELL", "MEDIUM_SELL", "TOP", "MOMENTUM_SELL"]
    never_eligible = [s for s in all_signals if s not in eligible_counter]
    print(f"\n  سیگنال‌هایی که هرگز شرایطشان برقرار نبوده:")
    for s in never_eligible:
        print(f"    - {s}")

    print("\n" + "=" * 62)
    print("END — read-only")
    print("=" * 62)


if __name__ == "__main__":
    main()
