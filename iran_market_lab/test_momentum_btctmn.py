import json
import os
import math
from datetime import datetime, timezone

DATA_FILE = "data/BTCTMN_4h.json"

# ─── Pure Python Indicators ───

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


def highest_high(candles, period):
    if len(candles) < period: return None
    return max(c["h"] for c in candles[-period:])


# ─── Momentum Strategy Backtest ───

def backtest_momentum(candles):
    equity = 1000.0
    equity_curve = [equity]
    trades = []
    fee_rate = 0.002  # 0.2% commission
    
    # Position state
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0  # how much capital is in this position
    trailing_stop = 0.0
    highest_since_entry = 0.0
    
    RISK_PER_TRADE_PCT = 0.01  # 1% of equity at risk
    ATR_MULTIPLIER = 2.0
    
    for i in range(60, len(candles)):
        window = candles[i-50:i+1]
        closes = [c["c"] for c in window]
        current = candles[i]
        price = current["c"]
        
        # Indicators
        sma50 = sma(closes, 50)
        rsi_val = rsi(closes, 14)
        atr_val = atr(window, 14)
        hh20 = highest_high(window, 20)
        
        if None in (sma50, rsi_val, atr_val, hh20):
            continue
        
        if in_position:
            # Update highest price since entry
            if price > highest_since_entry:
                highest_since_entry = price
                # Update trailing stop (raise it)
                new_stop = highest_since_entry - (ATR_MULTIPLIER * atr_val)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            # Exit check 1: Trailing Stop hit
            exit_reason = None
            exit_price = price
            if price <= trailing_stop:
                exit_reason = "TRAILING_STOP"
                exit_price = trailing_stop
            # Exit check 2: Price below SMA50 (trend break)
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
            # Entry conditions:
            # 1. Price above SMA50 (uptrend)
            # 2. RSI between 40 and 70 (not overbought/oversold)
            # 3. Price breaks above 20-candle high
            if (price > sma50 and 
                40 < rsi_val < 70 and 
                price > hh20 * 1.001):  # 0.1% buffer for real breakout
                
                in_position = True
                entry_price = price
                highest_since_entry = price
                trailing_stop = price - (ATR_MULTIPLIER * atr_val)
                
                # Position sizing based on risk
                risk_amount = equity * RISK_PER_TRADE_PCT
                stop_distance = ATR_MULTIPLIER * atr_val
                if stop_distance > 0:
                    units = risk_amount / stop_distance
                    position_size_usd = units * price
                    # Cap at max equity per trade
                    if position_size_usd > equity:
                        position_size_usd = equity
    
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
    
    print(f"=== Momentum Strategy Backtest on BTCTMN ===")
    print(f"Data points: {len(candles)}")
    print(f"First: {datetime.fromtimestamp(candles[0]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Last:  {datetime.fromtimestamp(candles[-1]['t'], tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Strategy: SMA50 + RSI(40-70) + 20-candle Breakout + ATR Trailing Stop\n")
    
    trades, equity_curve = backtest_momentum(candles)
    
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
