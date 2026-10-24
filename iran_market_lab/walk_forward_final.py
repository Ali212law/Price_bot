import json
import os
from datetime import datetime, timezone

# ─── Fee Structure (Ramzinex) ───
FEE_MAKER = 0.00095
FEE_TAKER = 0.0020

# ─── Winning Strategies (Based on Final Matrix) ───
WINNING_STRATEGIES = {
    "BTCTMN": "BH",
    "ETHTMN": "Momentum",
    "SOLTMN": "Momentum",
    "XRPTMN": "Momentum",
    "ADATMN": "Momentum",
    "DOGETMN": "Momentum",
    "BNBTMN": "BH",
    "TRXTMN": "BH",
    "LINKTMN": "Momentum",
    "AVAXTMN": "Grid",
    "DOTTMN": "Momentum",
}

DATA_DIR = "data"

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

def run_bh(candles):
    if len(candles) < 10: return []
    first_price = candles[0]["c"]
    fee_rate = FEE_MAKER + FEE_TAKER
    net = ((candles[-1]["c"] / first_price) - 1) - fee_rate
    return [net]

def run_momentum(candles):
    if len(candles) < 60: return []
    trades = []
    fee_rate = FEE_MAKER + FEE_TAKER
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0
    trailing_stop = 0.0
    highest_since_entry = 0.0
    equity = 1000.0
    
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
                equity += position_size_usd * net
                trades.append(net)
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
    return trades

def run_grid(candles):
    if len(candles) < 60: return []
    trades = []
    equity = 1000.0
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
                net = gross - (FEE_MAKER * 2)
                equity += (total_invested * net)
                trades.append(net)
                in_position = False
                continue
            if price <= initial_entry * 0.90:
                gross = (price - avg_entry) / avg_entry
                net = gross - (FEE_MAKER + FEE_TAKER)
                equity += (total_invested * net)
                trades.append(net)
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
    return trades

def main():
    print("=== Walk-Forward Analysis (Final Strategies, Ramzinex Fees) ===\n")
    
    for symbol, strategy in WINNING_STRATEGIES.items():
        data_file = f"{DATA_DIR}/{symbol}_4h.json"
        if not os.path.exists(data_file):
            continue
            
        with open(data_file, 'r') as f:
            candles = json.load(f)
            
        chunk = len(candles) // 4
        print(f"--- {symbol} (Strategy: {strategy}) ---")
        
        profitable_windows = 0
        total_trades_all = 0
        
        for i in range(4):
            start = i * chunk
            end = (i + 1) * chunk if i < 3 else len(candles)
            window = candles[start:end]
            
            if strategy == "BH":
                trades = run_bh(window)
            elif strategy == "Momentum":
                trades = run_momentum(window)
            elif strategy == "Grid":
                trades = run_grid(window)
            else:
                trades = []
                
            total_trades_all += len(trades)
            
            if trades:
                # محاسبه بازدهی ساده (Compound)
                eq = 1000.0
                for t in trades:
                    eq += eq * t
                pnl = ((eq - 1000) / 1000) * 100
                status = "PROFIT" if pnl > 0 else "LOSS"
                if pnl > 0: profitable_windows += 1
                print(f"  Window {i+1}: Trades={len(trades):3} | PnL={pnl:+.2f}% [{status}]")
            else:
                print(f"  Window {i+1}: No trades.")
        
        verdict = "PASS" if profitable_windows >= 3 else ("BORDERLINE" if profitable_windows == 2 else "FAIL")
        print(f"  -> Result: {profitable_windows}/4 Profitable Windows | Total Trades: {total_trades_all} [{verdict}]\n")

if __name__ == "__main__":
    main()
