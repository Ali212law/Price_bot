import json
import os

# ─── Fee Structure (Ramzinex) ───
FEE_MAKER = 0.00095
FEE_TAKER = 0.0020

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

def run_current_momentum(candles):
    """حالت فعلی: خروج فقط با Trailing Stop (Taker)"""
    trades = []
    in_position = False
    entry_price = 0.0
    trailing_stop = 0.0
    highest = 0.0
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
        
        if None in (sma50, rsi_val, atr_val, hh20): continue
        
        if in_position:
            if price > highest:
                highest = price
                new_stop = highest - (2.0 * atr_val)
                if new_stop > trailing_stop: trailing_stop = new_stop
            
            exit_price = None
            if price <= trailing_stop: exit_price = trailing_stop
            elif price < sma50: exit_price = price
            
            if exit_price:
                gross = (exit_price - entry_price) / entry_price
                net = gross - (FEE_MAKER + FEE_TAKER)
                equity += (equity * net * 0.1)
                trades.append(net)
                in_position = False
        else:
            if (price > sma50 and 40 < rsi_val < 80 and candles[i-1]["c"] <= hh20 and price > hh20):
                in_position = True
                entry_price = price
                highest = price
                trailing_stop = price - (2.0 * atr_val)
    return trades

def run_optimized_momentum(candles):
    """حالت بهینه: خروج هیبریدی (TP با Maker + Trailing Stop با Taker)"""
    trades = []
    in_position = False
    entry_price = 0.0
    trailing_stop = 0.0
    highest = 0.0
    tp_price = 0.0
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
        
        if None in (sma50, rsi_val, atr_val, hh20): continue
        
        if in_position:
            if price > highest:
                highest = price
                new_stop = highest - (2.0 * atr_val)
                if new_stop > trailing_stop: trailing_stop = new_stop
            
            # 1. Check Take Profit (Maker Fee)
            if price >= tp_price:
                gross = (tp_price - entry_price) / entry_price
                net = gross - (FEE_MAKER + FEE_MAKER)
                equity += (equity * net * 0.1)
                trades.append(net)
                in_position = False
                continue
                
            # 2. Check Trailing Stop (Taker Fee)
            exit_price = None
            if price <= trailing_stop: exit_price = trailing_stop
            elif price < sma50: exit_price = price
            
            if exit_price:
                gross = (exit_price - entry_price) / entry_price
                net = gross - (FEE_MAKER + FEE_TAKER)
                equity += (equity * net * 0.1)
                trades.append(net)
                in_position = False
        else:
            if (price > sma50 and 40 < rsi_val < 80 and candles[i-1]["c"] <= hh20 and price > hh20):
                in_position = True
                entry_price = price
                highest = price
                trailing_stop = price - (2.0 * atr_val)
                tp_price = price + (3.0 * atr_val) # TP در 3 برابر ATR
    return trades

def calculate_metrics(trades, name):
    if not trades:
        print(f"{name}: No trades.")
        return
    trades = np.array(trades) if 'np' in globals() else trades
    # Simple sum of returns for comparison (since position sizing is simplified)
    total_return = sum(trades) * 100
    wins = sum(1 for t in trades if t > 0)
    win_rate = (wins / len(trades)) * 100
    print(f"{name}: Trades={len(trades)} | WinRate={win_rate:.1f}% | Total Return (Sum)={total_return:+.2f}%")

if __name__ == "__main__":
    for symbol in ["ETHTMN", "XRPTMN"]:
        path = f"data/{symbol}_4h.json"
        if not os.path.exists(path): continue
        
        with open(path, 'r') as f:
            candles = json.load(f)
            
        print(f"\n=== Testing {symbol} ===")
        trades_current = run_current_momentum(candles)
        trades_optimized = run_optimized_momentum(candles)
        
        calculate_metrics(trades_current, "Current (Trailing Stop Only)")
        calculate_metrics(trades_optimized, "Optimized (Hybrid TP + Trailing Stop)")
