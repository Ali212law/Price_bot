import json
import os
import math
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denom


def backtest_pure_trend(candles):
    """Always in market. Exit only on ATR trailing stop. Re-enter next candle."""
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    fee_rate = 0.002
    
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0
    trailing_stop = 0.0
    highest_since_entry = 0.0
    
    RISK_PER_TRADE_PCT = 0.01
    ATR_MULTIPLIER = 2.0
    
    # Skip warmup
    for i in range(60, len(candles)):
        window = candles[i-14:i+1]
        current = candles[i]
        price = current["c"]
        atr_val = atr(window, 14)
        
        if atr_val is None or atr_val <= 0:
            continue
        
        if in_position:
            # Update trailing stop (only up)
            if price > highest_since_entry:
                highest_since_entry = price
                new_stop = highest_since_entry - (ATR_MULTIPLIER * atr_val)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            # Check exit
            if price <= trailing_stop:
                exit_price = trailing_stop
                gross = (exit_price - entry_price) / entry_price
                net = gross - fee_rate
                pnl_usd = position_size_usd * net
                equity += pnl_usd
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
        
        # Enter if not in position (immediately after exit or on first candle)
        if not in_position:
            in_position = True
            entry_price = price
            highest_since_entry = price
            trailing_stop = price - (ATR_MULTIPLIER * atr_val)
            
            risk_amount = equity * RISK_PER_TRADE_PCT
            stop_distance = ATR_MULTIPLIER * atr_val
            if stop_distance > 0:
                units = risk_amount / stop_distance
                position_size_usd = units * price
                if position_size_usd > equity:
                    position_size_usd = equity
    
    # Close final position if still open
    if in_position:
        exit_price = candles[-1]["c"]
        gross = (exit_price - entry_price) / entry_price
        net = gross - fee_rate
        pnl_usd = position_size_usd * net
        equity += pnl_usd
        trades.append(net)
        equity_curve.append(equity)
    
    return trades, equity_curve


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== Pure Trend Follow Backtest on BTCTMN ===")
    print(f"Data points: {len(candles)}")
    print(f"First: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Last:  {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Strategy: Always-in, ATRx2 trailing stop, re-enter after exit\n")
    
    trades, equity_curve = backtest_pure_trend(candles)
    
    if not trades:
        print("No trades generated.")
        return
    
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_count = len(wins)
    total = len(trades)
    
    net_pnl = ((equity_curve[-1] - 1000) / 1000) * 100
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    avg_win = (sum(wins) / len(wins)) if wins else 0
    avg_loss = (abs(sum(losses)) / len(losses)) if losses else 0
    win_rate = win_count / total
    expectancy = (win_rate * (avg_win / 0.01)) - ((1 - win_rate) * (avg_loss / 0.01))
    
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
    
    wilson = calculate_wilson_lower(win_count, total) * 100
    
    print(f"Total Trades: {total}")
    print(f"Wins: {win_count} | Losses: {total - win_count}")
    print(f"Win Rate: {win_rate * 100:.1f}%")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Final Equity: ${equity_curve[-1]:.2f}")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R")
    print(f"Max Drawdown: {max_dd * 100:.2f}%")
    print(f"Wilson Lower Bound: {wilson:.2f}%")
    
    print("\n--- Gate D-68-Plus Check ---")
    print(f"n >= 30:         {'PASS' if total >= 30 else 'FAIL'} ({total})")
    print(f"PF > 1.2:        {'PASS' if pf > 1.2 else 'FAIL'} ({pf:.2f})")
    print(f"Expectancy>0.1R: {'PASS' if expectancy > 0.1 else 'FAIL'} ({expectancy:.3f})")
    print(f"MaxDD < 15%:     {'PASS' if max_dd*100 < 15 else 'FAIL'} ({max_dd*100:.2f}%)")
    print(f"Wilson > 36%:    {'PASS' if wilson > 36 else 'FAIL'} ({wilson:.2f}%)")


if __name__ == "__main__":
    main()
