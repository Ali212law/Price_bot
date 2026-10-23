import json
import os
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


def backtest_pure_trend(candles, risk_pct=0.005, atr_mult=2.0):
    """Always-in, ATR trailing stop, no same-candle re-entry."""
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    fee_rate = 0.002
    total_fees = 0.0
    position_sizes = []
    
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0
    trailing_stop = 0.0
    highest_since_entry = 0.0
    just_exited = False
    
    for i in range(60, len(candles)):
        window = candles[i-14:i+1]
        current = candles[i]
        price_close = current["c"]
        price_low = current["l"]
        atr_val = atr(window, 14)
        
        if atr_val is None or atr_val <= 0:
            continue
        
        if in_position:
            if price_close > highest_since_entry:
                highest_since_entry = price_close
                new_stop = highest_since_entry - (atr_mult * atr_val)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            if price_low <= trailing_stop:
                exit_price = trailing_stop
                if current["o"] < trailing_stop:
                    exit_price = current["o"]
                
                gross = (exit_price - entry_price) / entry_price
                net = gross - fee_rate
                fee_usd = position_size_usd * fee_rate
                total_fees += fee_usd
                pnl_usd = position_size_usd * net
                equity += pnl_usd
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                just_exited = True
        
        if not in_position and not just_exited:
            if atr_val > 0:
                in_position = True
                entry_price = price_close
                highest_since_entry = price_close
                trailing_stop = price_close - (atr_mult * atr_val)
                
                risk_amount = equity * risk_pct
                stop_distance = atr_mult * atr_val
                if stop_distance > 0:
                    units = risk_amount / stop_distance
                    position_size_usd = units * entry_price
                    if position_size_usd > equity:
                        position_size_usd = equity
                    position_sizes.append(position_size_usd / equity)
        
        # Reset just_exited flag after one candle
        if just_exited and i > 0:
            # We're at the end of iteration; next iteration will allow entry
            just_exited = False
    
    # Close final position
    if in_position:
        exit_price = candles[-1]["c"]
        gross = (exit_price - entry_price) / entry_price
        net = gross - fee_rate
        total_fees += position_size_usd * fee_rate
        pnl_usd = position_size_usd * net
        equity += pnl_usd
        trades.append(net)
        equity_curve.append(equity)
    
    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "total_fees": total_fees,
        "avg_position_pct": (sum(position_sizes) / len(position_sizes) * 100) if position_sizes else 0
    }


def backtest_buy_and_hold(candles):
    """Buy at first, sell at last. Minimal fee."""
    first_price = candles[60]["c"]  # Start at same warmup
    last_price = candles[-1]["c"]
    fee_rate = 0.002
    net_return = ((last_price - first_price) / first_price) - fee_rate
    final_equity = 1000.0 * (1 + net_return)
    
    return {
        "trades": [net_return],
        "equity_curve": [1000.0, final_equity],
        "total_fees": 1000.0 * fee_rate,
        "avg_position_pct": 100.0
    }


def calculate_metrics(result):
    trades = result["trades"]
    equity_curve = result["equity_curve"]
    
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
        "calmar": calmar,
        "fees": result["total_fees"],
        "avg_pos_pct": result["avg_position_pct"]
    }


def print_result(name, m, bh_pnl=None):
    if m is None:
        print(f"--- {name} ---")
        print(f"  No trades generated.\n")
        return
    
    print(f"--- {name} ---")
    print(f"  Trades:        {m['n']}")
    print(f"  Win Rate:      {m['win_rate']:.1f}%")
    print(f"  Net PnL:       {m['net_pnl']:+.2f}%")
    print(f"  Max DD:        {m['max_dd']:.2f}%")
    print(f"  Calmar Ratio:  {m['calmar']:.2f}")
    print(f"  PF:            {m['pf']:.2f}")
    print(f"  Total Fees:    ${m['fees']:.2f}")
    print(f"  Avg Position:  {m['avg_pos_pct']:.1f}% of equity")
    if bh_pnl is not None:
        print(f"  vs B&H:        {m['net_pnl'] - bh_pnl:+.2f}%")
    print()


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== Multi-ATR Trend Follow Test on BTCTMN ===")
    print(f"Data: {len(candles)} candles")
    print(f"First: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Last:  {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Risk per trade: 0.5% | Fee: 0.2% round-trip\n")
    
    # 1. Buy & Hold
    bh_result = backtest_buy_and_hold(candles)
    bh_metrics = calculate_metrics(bh_result)
    print_result("1. Buy & Hold (Benchmark)", bh_metrics)
    bh_pnl = bh_metrics["net_pnl"]
    
    # 2-5. Pure Trend with different ATR multipliers
    for atr_mult in [2, 4, 6, 8]:
        result = backtest_pure_trend(candles, risk_pct=0.005, atr_mult=atr_mult)
        metrics = calculate_metrics(result)
        print_result(f"{atr_mult+1}. Pure Trend ATRx{atr_mult}", metrics, bh_pnl)
    
    print("=== Summary ===")
    print("Best Calmar Ratio = Best risk-adjusted strategy")
    print("(Calmar = Net PnL / MaxDD, higher is better)")


if __name__ == "__main__":
    main()
