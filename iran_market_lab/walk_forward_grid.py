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


def run_safe_grid(candles):
    """Safe Grid strategy on a candle slice."""
    if len(candles) < 100:
        return [], [1000.0]
    
    equity = 1000.0
    equity_curve = [equity]
    trades = []
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
        
        if None in (lower_bb, rsi_val):
            continue
        
        if in_position:
            avg_entry = total_invested / total_units
            
            if price >= avg_entry * 1.02:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
                equity += (total_invested * net)
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                continue
            
            if price <= initial_entry * 0.90:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
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
    
    return trades, equity_curve


def calculate_metrics(trades, equity_curve):
    if not trades:
        return {"n": 0, "net_pnl": 0, "pf": 0, "max_dd": 0}
    
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
    
    return {
        "n": len(trades),
        "net_pnl": net_pnl,
        "pf": pf,
        "max_dd": max_dd * 100
    }


def walk_forward(symbol, data_file, num_windows=4):
    if not os.path.exists(data_file):
        print(f"{symbol}: File not found")
        return None
    
    with open(data_file, 'r') as f:
        candles = json.load(f)
    
    if len(candles) < 500:
        print(f"{symbol}: Not enough data")
        return None
    
    print(f"\n{'='*70}")
    print(f"  {symbol} — Safe Grid Walk-Forward")
    print(f"  Total candles: {len(candles)}")
    print(f"{'='*70}\n")
    
    chunk = len(candles) // num_windows
    profitable = 0
    
    for i in range(num_windows):
        start = i * chunk
        end = (i + 1) * chunk if i < num_windows - 1 else len(candles)
        window = candles[start:end]
        
        if len(window) < 100:
            print(f"  Window {i+1}: TOO SMALL")
            continue
        
        start_dt = datetime.fromtimestamp(window[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        end_dt = datetime.fromtimestamp(window[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        
        trades, curve = run_safe_grid(window)
        m = calculate_metrics(trades, curve)
        
        status = "PROFIT" if m['net_pnl'] > 0 else "LOSS"
        if m['net_pnl'] > 0:
            profitable += 1
        
        print(f"  Window {i+1} ({start_dt} -> {end_dt})")
        print(f"    Trades: {m['n']} | Net PnL: {m['net_pnl']:+.2f}% | PF: {m['pf']:.2f} | MaxDD: {m['max_dd']:.2f}% [{status}]")
    
    print(f"\n  Summary: {profitable}/{num_windows} profitable windows")
    if profitable >= 3:
        print(f"  VERDICT: PASS")
        return "PASS"
    elif profitable == 2:
        print(f"  VERDICT: BORDERLINE")
        return "BORDERLINE"
    else:
        print(f"  VERDICT: FAIL")
        return "FAIL"


def main():
    assets = [
        ("DOTTMN", "data/DOTTMN_4h.json"),
        ("AVAXTMN", "data/AVAXTMN_4h.json"),
        ("LINKTMN", "data/LINKTMN_4h.json"),
    ]
    
    results = {}
    for symbol, path in assets:
        results[symbol] = walk_forward(symbol, path)
    
    print(f"\n{'='*70}")
    print(f"  FINAL VERDICT")
    print(f"{'='*70}")
    for symbol, verdict in results.items():
        if verdict:
            print(f"  {symbol}: {verdict}")


if __name__ == "__main__":
    main()
