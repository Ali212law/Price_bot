import json
import os
from datetime import datetime, timezone


def sma(values, period):
    if len(values) < period: return None
    return sum(values[-period:]) / period


def std_dev(values, period, mean):
    if len(values) < period: return None
    window = values[-period:]
    variance = sum((x - mean) ** 2 for x in window) / period
    return variance ** 0.5


def rsi(closes, period=14):
    if len(closes) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + (avg_gain / avg_loss)))


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


def calculate_metrics(equity_curve, trades, fee_total=0):
    if not trades:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    net_pnl = ((equity_curve[-1] - 1000) / 1000) * 100
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
    calmar = net_pnl / (max_dd * 100) if max_dd > 0 else 0
    return {"n": len(trades), "net_pnl": net_pnl, "pf": pf, "max_dd": max_dd * 100, "calmar": calmar, "fees": fee_total}


def run_bh(candles):
    first_price = candles[60]["c"]
    fee_rate = 0.002
    equity_curve = [1000.0]
    for i in range(60, len(candles)):
        price = candles[i]["c"]
        equity_curve.append(1000.0 * (price / first_price) * (1 - fee_rate))
    net = (equity_curve[-1] - 1000.0) / 1000.0
    return [net], equity_curve, 1000.0 * fee_rate


def run_grid(candles):
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    fee_total = 0.0
    fee_rate = 0.002
    in_position = False
    levels = 0
    total_invested = 0.0
    total_units = 0.0
    initial_entry = 0.0
    for i in range(50, len(candles)):
        window = candles[i-50:i]
        closes = [c["c"] for c in window]
        current = candles[i]
        price = current["c"]
        mean = sma(closes, 20)
        std = std_dev(closes, 20, mean) if mean else None
        lower_bb = (mean - 2 * std) if (mean and std) else None
        rsi_val = rsi(closes, 14)
        if None in (lower_bb, rsi_val): continue
        if in_position:
            avg_entry = total_invested / total_units
            if price >= avg_entry * 1.02:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
                fee_total += total_invested * fee_rate
                equity += (total_invested * net)
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                continue
            if price <= initial_entry * 0.90:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
                fee_total += total_invested * fee_rate
                equity += (total_invested * net)
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                continue
            if levels == 1 and price <= initial_entry * 0.97:
                amount = equity / 3
                total_units += amount / price
                total_invested += amount
                levels = 2
            elif levels == 2 and price <= initial_entry * 0.94:
                amount = equity / 3
                total_units += amount / price
                total_invested += amount
                levels = 3
        else:
            if price <= lower_bb and rsi_val < 35:
                in_position = True
                levels = 1
                initial_entry = price
                amount = equity / 3
                total_units = amount / price
                total_invested = amount
    return trades, equity_curve, fee_total


def run_momentum(candles):
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    fee_total = 0.0
    fee_rate = 0.002
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0
    trailing_stop = 0.0
    highest_since_entry = 0.0
    for i in range(60, len(candles)):
        window = candles[i-50:i+1]
        closes = [c["c"] for c in window]
        current = candles[i]
        price = current["c"]
        sma50 = sma(closes, 50)
        rsi_val = rsi(closes, 14)
        atr_val = atr(window, 14)
        prev_20 = candles[i-20:i]
        hh20 = max(c["h"] for c in prev_20) if len(prev_20) == 20 else None
        prev_close = candles[i-1]["c"]
        if None in (sma50, rsi_val, atr_val, hh20): continue
        if in_position:
            if price > highest_since_entry:
                highest_since_entry = price
                new_stop = highest_since_entry - (2.0 * atr_val)
                if new_stop > trailing_stop: trailing_stop = new_stop
            exit_price = None
            if price <= trailing_stop: exit_price = trailing_stop
            elif price < sma50: exit_price = price
            if exit_price:
                gross = (exit_price - entry_price) / entry_price
                net = gross - fee_rate
                fee_total += position_size_usd * fee_rate
                equity += position_size_usd * net
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
        else:
            if (price > sma50 and 40 < rsi_val < 80 and prev_close <= hh20 and price > hh20):
                in_position = True
                entry_price = price
                highest_since_entry = price
                trailing_stop = price - (2.0 * atr_val)
                risk_amount = equity * 0.01
                stop_distance = 2.0 * atr_val
                if stop_distance > 0:
                    units = risk_amount / stop_distance
                    position_size_usd = units * price
                    if position_size_usd > equity: position_size_usd = equity
    return trades, equity_curve, fee_total


def test_asset(symbol, data_file):
    if not os.path.exists(data_file):
        print(f"  {symbol}: File not found ({data_file})")
        return {}
    with open(data_file, 'r') as f:
        candles = json.load(f)
    if len(candles) < 200:
        print(f"  {symbol}: Not enough data ({len(candles)})")
        return {}
    print(f"\n{'='*70}")
    print(f"  {symbol} - {len(candles)} candles")
    print(f"  Range: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"  Price: {candles[0]['c']:,.0f} -> {candles[-1]['c']:,.0f}")
    print(f"{'='*70}\n")
    results = {}
    trades, curve, fees = run_bh(candles)
    results["Buy & Hold"] = calculate_metrics(curve, trades, fees)
    trades, curve, fees = run_grid(candles)
    results["Safe Grid"] = calculate_metrics(curve, trades, fees)
    trades, curve, fees = run_momentum(candles)
    results["Momentum"] = calculate_metrics(curve, trades, fees)
    print(f"{'Strategy':<20} {'Trades':>8} {'Net PnL':>12} {'MaxDD':>10} {'PF':>8} {'Calmar':>8}")
    print(f"{'-'*20} {'-'*8} {'-'*12} {'-'*10} {'-'*8} {'-'*8}")
    for name, m in results.items():
        if m is None:
            print(f"{name:<20} {'-':>8} {'-':>12} {'-':>10} {'-':>8} {'-':>8}")
        else:
            print(f"{name:<20} {m['n']:>8} {m['net_pnl']:>+11.2f}% {m['max_dd']:>9.2f}% {m['pf']:>8.2f} {m['calmar']:>8.2f}")
    return results


def main():
    assets = [
        ("BTCTMN", "data/BTCTMN_4h.json"),
        ("ETHTMN", "data/ETHTMN_4h.json"),
        ("SOLTMN", "data/SOLTMN_4h.json"),
        ("XRPTMN", "data/XRPTMN_4h.json"),
        ("ADATMN", "data/ADATMN_4h.json"),
        ("DOGETMN", "data/DOGETMN_4h.json"),
        ("BNBTMN", "data/BNBTMN_4h.json"),
        ("TRXTMN", "data/TRXTMN_4h.json"),
        ("LINKTMN", "data/LINKTMN_4h.json"),
        ("AVAXTMN", "data/AVAXTMN_4h.json"),
        ("DOTTMN", "data/DOTTMN_4h.json"),
    ]
    all_results = {}
    for symbol, path in assets:
        all_results[symbol] = test_asset(symbol, path)
    print(f"\n{'='*70}")
    print(f"  FINAL MATRIX: Best Strategy per Asset (by Calmar)")
    print(f"{'='*70}")
    print(f"{'Asset':<10} {'Best Strategy':<20} {'Calmar':>8} {'Net PnL':>12} {'MaxDD':>10}")
    print(f"{'-'*10} {'-'*20} {'-'*8} {'-'*12} {'-'*10}")
    for symbol, results in all_results.items():
        best = None
        best_calmar = -999
        for name, m in results.items():
            if m and m['calmar'] > best_calmar:
                best_calmar = m['calmar']
                best = (name, m)
        if best:
            print(f"{symbol:<10} {best[0]:<20} {best_calmar:>8.2f} {best[1]['net_pnl']:>+11.2f}% {best[1]['max_dd']:>9.2f}%")


if __name__ == "__main__":
    main()
