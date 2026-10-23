import json
import os
from datetime import datetime, timezone


def sma(values, period):
    if len(values) < period: return None
    return sum(values[-period:]) / period


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


def backtest_momentum(candles):
    """Momentum strategy for a given candle slice."""
    if len(candles) < 100:
        return [], [1000.0]
    
    equity = 1000.0
    equity_curve = [equity]
    trades = []
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
        
        if None in (sma50, rsi_val, atr_val, hh20):
            continue
        
        if in_position:
            if price > highest_since_entry:
                highest_since_entry = price
                new_stop = highest_since_entry - (2.0 * atr_val)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            exit_price = None
            if price <= trailing_stop:
                exit_price = trailing_stop
            elif price < sma50:
                exit_price = price
            
            if exit_price:
                gross = (exit_price - entry_price) / entry_price
                net = gross - fee_rate
                equity += position_size_usd * net
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
        else:
            if (price > sma50 and 40 < rsi_val < 80 and 
                prev_close <= hh20 and price > hh20):
                in_position = True
                entry_price = price
                highest_since_entry = price
                trailing_stop = price - (2.0 * atr_val)
                risk_amount = equity * 0.01
                stop_distance = 2.0 * atr_val
                if stop_distance > 0:
                    units = risk_amount / stop_distance
                    position_size_usd = units * price
                    if position_size_usd > equity:
                        position_size_usd = equity
    
    return trades, equity_curve


def backtest_bh(candles):
    """Buy & Hold for a given candle slice."""
    if len(candles) < 2:
        return [], [1000.0]
    
    first_price = candles[0]["c"]
    fee_rate = 0.002
    equity_curve = [1000.0]
    for c in candles:
        price = c["c"]
        equity_curve.append(1000.0 * (price / first_price) * (1 - fee_rate))
    
    net = (equity_curve[-1] - 1000.0) / 1000.0
    return [net], equity_curve


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


def walk_forward_test(symbol, data_file, strategy_name, strategy_func, num_windows=4):
    """Runs walk-forward test."""
    if not os.path.exists(data_file):
        print(f"⚠️ {symbol}: File not found ({data_file})")
        return None
    
    with open(data_file, 'r') as f:
        candles = json.load(f)
    
    if len(candles) < 500:
        print(f"⚠️ {symbol}: Not enough data")
        return None
    
    print(f"\n{'='*70}")
    print(f"  {symbol} — Strategy: {strategy_name}")
    print(f"  Total candles: {len(candles)}")
    print(f"{'='*70}\n")
    
    chunk = len(candles) // num_windows
    profitable = 0
    results = []
    
    for i in range(num_windows):
        start = i * chunk
        end = (i + 1) * chunk if i < num_windows - 1 else len(candles)
        window = candles[start:end]
        
        if len(window) < 100:
            print(f"  Window {i+1}: TOO SMALL")
            continue
        
        start_dt = datetime.fromtimestamp(window[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        end_dt = datetime.fromtimestamp(window[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        
        trades, equity_curve = strategy_func(window)
        m = calculate_metrics(trades, equity_curve)
        
        status = "✅ PROFIT" if m['net_pnl'] > 0 else "❌ LOSS"
        if m['net_pnl'] > 0:
            profitable += 1
        
        print(f"  Window {i+1} ({start_dt} → {end_dt})")
        print(f"    Trades: {m['n']} | Net PnL: {m['net_pnl']:+.2f}% | PF: {m['pf']:.2f} | MaxDD: {m['max_dd']:.2f}% {status}")
        results.append(m)
    
    print(f"\n  ─── Summary ───")
    print(f"  Profitable Windows: {profitable}/{num_windows}")
    
    if profitable >= 3:
        print(f"  ✅ WALK-FORWARD PASS")
        verdict = "PASS"
    elif profitable == 2:
        print(f"  ⚠️ WALK-FORWARD BORDERLINE")
        verdict = "BORDERLINE"
    else:
        print(f"  ❌ WALK-FORWARD FAIL")
        verdict = "FAIL"
    
    return {"verdict": verdict, "profitable": profitable, "total": num_windows, "results": results}


def main():
    print("=" * 70)
    print("  WALK-FORWARD TEST — Top 2 Winning Strategies")
    print("=" * 70)
    
    # ETH with Momentum
    eth_result = walk_forward_test(
        "ETHTMN",
        "data/ETHTMN_4h.json",
        "Momentum",
        backtest_momentum
    )
    
    # XRP with Buy & Hold
    xrp_result = walk_forward_test(
        "XRPTMN",
        "data/XRPTMN_4h.json",
        "Buy & Hold",
        backtest_bh
    )
    
    # Final summary
    print(f"\n{'='*70}")
    print(f"  🏆 FINAL VERDICT")
    print(f"{'='*70}")
    
    if eth_result:
        print(f"  ETHTMN + Momentum:    {eth_result['verdict']} ({eth_result['profitable']}/{eth_result['total']} profitable)")
    if xrp_result:
        print(f"  XRPTMN + Buy & Hold:  {xrp_result['verdict']} ({xrp_result['profitable']}/{xrp_result['total']} profitable)")
    
    print()
    if eth_result and xrp_result:
        if eth_result['verdict'] == "PASS" and xrp_result['verdict'] == "PASS":
            print(f"  🎉 BOTH STRATEGIES PASSED → Ready for M11-IR")
        elif eth_result['verdict'] == "PASS" or xrp_result['verdict'] == "PASS":
            print(f"  ⚠️ Only one passed → Use the passing one for M11-IR")
        else:
            print(f"  ❌ Both failed → Revisit strategy selection")


if __name__ == "__main__":
    main()
