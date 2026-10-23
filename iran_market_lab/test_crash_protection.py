import json
import os
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"


def calculate_metrics(equity_curve, trades):
    if not trades:
        return None
    
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_count = len(wins)
    total = len(trades)
    
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
    
    return {
        "n": total,
        "win_rate": (win_count / total) * 100 if total > 0 else 0,
        "net_pnl": net_pnl,
        "pf": pf,
        "max_dd": max_dd * 100,
        "calmar": calmar
    }


def backtest_buy_and_hold(candles):
    """B&H with proper equity tracking."""
    first_price = candles[60]["c"]
    fee_rate = 0.002
    equity_curve = [1000.0]
    for i in range(60, len(candles)):
        price = candles[i]["c"]
        value = 1000.0 * (price / first_price) * (1 - fee_rate)
        equity_curve.append(value)
    net = (equity_curve[-1] - 1000.0) / 1000.0
    return [net], equity_curve


def backtest_crash_protection(candles, crash_pct=0.40, recovery_pct=0.15, fee_rate=0.002):
    """Stay in market, exit on crash (X% from peak), re-enter on recovery (Y% from bottom)."""
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    
    in_position = False
    entry_price = 0.0
    position_value = 0.0
    peak_price = 0.0
    bottom_price = 0.0
    waiting_for_recovery = False
    
    for i in range(60, len(candles)):
        price = candles[i]["c"]
        
        if not in_position and not waiting_for_recovery:
            in_position = True
            entry_price = price
            peak_price = price
            position_value = equity
        
        elif in_position:
            if price > peak_price:
                peak_price = price
            
            if price <= peak_price * (1 - crash_pct):
                gross = (price - entry_price) / entry_price
                net = gross - fee_rate
                equity = position_value * (1 + net)
                trades.append(net)
                in_position = False
                waiting_for_recovery = True
                bottom_price = price
        
        elif waiting_for_recovery:
            if price < bottom_price:
                bottom_price = price
            
            if price >= bottom_price * (1 + recovery_pct):
                in_position = True
                entry_price = price
                peak_price = price
                position_value = equity
                waiting_for_recovery = False
        
        if in_position:
            current_value = position_value * (price / entry_price)
        else:
            current_value = equity
        equity_curve.append(current_value)
    
    if in_position:
        gross = (candles[-1]["c"] - entry_price) / entry_price
        net = gross - fee_rate
        equity = position_value * (1 + net)
        trades.append(net)
        equity_curve.append(equity)
    
    return trades, equity_curve


def print_result(name, metrics, bh_pnl=None):
    if metrics is None:
        print(f"--- {name} ---")
        print(f"  No trades generated.\n")
        return
    
    print(f"--- {name} ---")
    print(f"  Trades:        {metrics['n']}")
    print(f"  Win Rate:      {metrics['win_rate']:.1f}%")
    print(f"  Net PnL:       {metrics['net_pnl']:+.2f}%")
    print(f"  Max DD:        {metrics['max_dd']:.2f}%")
    print(f"  Calmar Ratio:  {metrics['calmar']:.2f}")
    print(f"  PF:            {metrics['pf']:.2f}")
    if bh_pnl is not None:
        print(f"  vs B&H:        {metrics['net_pnl'] - bh_pnl:+.2f}%")
    print()


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== B&H + Crash Protection on BTCTMN ===")
    print(f"Data: {len(candles)} candles")
    print(f"First: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Last:  {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Fee: 0.2% per round trip\n")
    
    bh_trades, bh_curve = backtest_buy_and_hold(candles)
    bh_metrics = calculate_metrics(bh_curve, bh_trades)
    print_result("1. Buy & Hold (Benchmark)", bh_metrics)
    bh_pnl = bh_metrics["net_pnl"]
    
    scenarios = [
        ("2. Crash 40%, Recover 10%", 0.40, 0.10),
        ("3. Crash 40%, Recover 15%", 0.40, 0.15),
        ("4. Crash 40%, Recover 20%", 0.40, 0.20),
        ("5. Crash 30%, Recover 15%", 0.30, 0.15),
        ("6. Crash 50%, Recover 15%", 0.50, 0.15),
    ]
    
    for name, crash, recover in scenarios:
        trades, curve = backtest_crash_protection(candles, crash_pct=crash, recovery_pct=recover)
        metrics = calculate_metrics(curve, trades)
        print_result(name, metrics, bh_pnl)
    
    print("=== Summary ===")
    print("Best = highest Calmar (return / drawdown)")
    print("Goal: Match B&H return while reducing MaxDD")


if __name__ == "__main__":
    main()
