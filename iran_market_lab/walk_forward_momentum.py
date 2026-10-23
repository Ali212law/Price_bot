import json
import os
import math
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"


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
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


def run_momentum(candles):
    """Runs Momentum strategy on a slice of candles."""
    if len(candles) < 60:
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
    
    RISK_PER_TRADE_PCT = 0.01
    ATR_MULTIPLIER = 2.0
    
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
                new_stop = highest_since_entry - (ATR_MULTIPLIER * atr_val)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            exit_reason = None
            exit_price = price
            if price <= trailing_stop:
                exit_reason = "TRAILING_STOP"
                exit_price = trailing_stop
            elif price < sma50:
                exit_reason = "TREND_BREAK"
            
            if exit_reason:
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                pnl_usd = position_size_usd * net_return
                equity += pnl_usd
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                continue
        
        else:
            if (price > sma50 and 
                40 < rsi_val < 80 and 
                prev_close <= hh20 and 
                price > hh20):
                
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
    
    return trades, equity_curve


def calculate_metrics(trades, equity_curve):
    if not trades:
        return 0, 0, 0, 0, 0
    
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
    
    return total, net_pnl, pf, expectancy, max_dd * 100


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== Walk-Forward Analysis: Momentum on BTCTMN ===")
    print(f"Total candles: {len(candles)}")
    print(f"Parameters LOCKED: SMA50, RSI(40-80), ATRx2 trailing, 1% risk")
    print()
    
    # Split into 4 windows
    chunk = len(candles) // 4
    
    profitable_windows = 0
    total_windows = 4
    
    for i in range(4):
        start = i * chunk
        end = (i + 1) * chunk if i < 3 else len(candles)
        window_candles = candles[start:end]
        
        if len(window_candles) < 100:
            print(f"--- Window {i+1}: TOO SMALL ({len(window_candles)} candles) ---\n")
            continue
        
        start_dt = datetime.fromtimestamp(window_candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        end_dt = datetime.fromtimestamp(window_candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')
        
        trades, equity_curve = run_momentum(window_candles)
        n, pnl, pf, exp, dd = calculate_metrics(trades, equity_curve)
        
        print(f"--- Window {i+1} ({start_dt} to {end_dt}) ---")
        print(f"Trades: {n} | Net PnL: {pnl:+.2f}% | PF: {pf:.2f} | Exp: {exp:+.3f}R | MaxDD: {dd:.2f}%")
        
        if pnl > 0:
            profitable_windows += 1
            print(f"✅ PROFITABLE")
        else:
            print(f"❌ LOSS")
        
        if n < 10:
            print(f"⚠️ Low trade count ({n})")
        print()
    
    print(f"=== Summary ===")
    print(f"Profitable Windows: {profitable_windows}/{total_windows}")
    
    if profitable_windows >= 3:
        print(f"✅ WALK-FORWARD PASS: Strategy is stable across time windows.")
    elif profitable_windows >= 2:
        print(f"⚠️ WALK-FORWARD BORDERLINE: Only {profitable_windows}/4 profitable.")
    else:
        print(f"❌ WALK-FORWARD FAIL: Only {profitable_windows}/4 profitable windows.")


if __name__ == "__main__":
    main()
