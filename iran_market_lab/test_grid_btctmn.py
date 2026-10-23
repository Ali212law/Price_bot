import json
import os
import math
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"

# ─── Pure Python Indicators ───

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
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def adx(candles, period=14):
    """ADX (Average Directional Index) without pandas."""
    if len(candles) < period * 2: return 0.0
    
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        h = candles[i]["h"]
        l = candles[i]["l"]
        prev_h = candles[i-1]["h"]
        prev_l = candles[i-1]["l"]
        prev_c = candles[i-1]["c"]
        
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        
        up = h - prev_h
        down = prev_l - l
        plus_dm.append(up if (up > down and up > 0) else 0)
        minus_dm.append(down if (down > up and down > 0) else 0)
    
    # Simple moving averages (Wilder's smoothing approximated with SMA for simplicity)
    atr_val = sum(trs[-period:]) / period
    if atr_val == 0: return 0.0
    
    plus_di = 100 * (sum(plus_dm[-period:]) / period) / atr_val
    minus_di = 100 * (sum(minus_dm[-period:]) / period) / atr_val
    
    di_sum = plus_di + minus_di
    if di_sum == 0: return 0.0
    
    dx = 100 * abs(plus_di - minus_di) / di_sum
    return dx

def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


# ─── Backtest Logic (Safe Grid) ───

def backtest_grid(candles):
    equity = 1000.0
    trades = []
    equity_curve = [equity]
    fee_rate = 0.002  # 0.2% commission
    
    # Position state
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
        
        # Indicators
        mean = sma(closes, 20)
        std = std_dev(closes, 20, mean) if mean else None
        lower_bb = (mean - 2 * std) if (mean and std) else None
        rsi_val = rsi(closes, 14)
        adx_val = adx(window, 14)
        atr_val = atr(window, 14)
        
        if None in (lower_bb, rsi_val, atr_val):
            continue
        
        if in_position:
            avg_entry = total_invested / total_units
            
            # Exit: TP (+2%)
            if price >= avg_entry * 1.02:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
                equity += (total_invested * net)
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                continue
            
            # Exit: Hard SL (-10% from initial entry)
            if price <= initial_entry * 0.90:
                gross = (price - avg_entry) / avg_entry
                net = gross - fee_rate
                equity += (total_invested * net)
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
                continue
            
            # Add Level 2 (at -3% from initial)
            if levels == 1 and price <= initial_entry * 0.97:
                amount = equity / 3
                total_units += amount / price
                total_invested += amount
                levels = 2
            
            # Add Level 3 (at -6% from initial)
            elif levels == 2 and price <= initial_entry * 0.94:
                amount = equity / 3
                total_units += amount / price
                total_invested += amount
                levels = 3
        
        else:
            # Entry: ADX < 25 (Range) + Price below Lower BB + RSI < 35
            if adx_val < 25 and price <= lower_bb and rsi_val < 35:
                in_position = True
                levels = 1
                initial_entry = price
                amount = equity / 3
                total_units = amount / price
                total_invested = amount
    
    return trades, equity_curve


def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denom


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== Safe Grid Backtest on BTCTMN ===")
    print(f"Data points: {len(candles)}")
    print(f"First: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Last:  {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}\n")
    
    trades, equity_curve = backtest_grid(candles)
    
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
