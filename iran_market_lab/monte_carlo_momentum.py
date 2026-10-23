import json
import os
import math
import random
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
    return 100 - (100 / (1 + (avg_gain / avg_loss)))


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


def run_actual_strategy(candles):
    """Runs the REAL Momentum strategy and returns list of trade returns."""
    if len(candles) < 100:
        return []
    
    trades = []
    fee_rate = 0.002
    
    in_position = False
    entry_price = 0.0
    position_size_usd = 0.0
    trailing_stop = 0.0
    highest_since_entry = 0.0
    equity = 1000.0
    
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
            
            exit_triggered = False
            exit_price = price
            if price <= trailing_stop:
                exit_triggered = True
                exit_price = trailing_stop
            elif price < sma50:
                exit_triggered = True
            
            if exit_triggered:
                gross = (exit_price - entry_price) / entry_price
                net = gross - fee_rate
                pnl_usd = position_size_usd * net
                equity += pnl_usd
                trades.append(net)
                in_position = False
                continue
        else:
            if (price > sma50 and 40 < rsi_val < 80 and 
                prev_close <= hh20 and price > hh20):
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
    
    return trades


def run_random_strategy(candles, num_trades, rng):
    """Runs a RANDOM entry strategy with same exit rules (trailing ATR).
    This is the correct null hypothesis: 'What if we had random entries
    but same exits?'"""
    if len(candles) < 100:
        return []
    
    trades = []
    fee_rate = 0.002
    equity = 1000.0
    RISK_PER_TRADE_PCT = 0.01
    ATR_MULTIPLIER = 2.0
    
    # Pick random entry indices (avoiding the last 60 which need exit window)
    available_indices = list(range(60, len(candles) - 60))
    rng.shuffle(available_indices)
    entry_indices = sorted(available_indices[:num_trades])
    
    for idx in entry_indices:
        # Entry at random candle
        entry_price = candles[idx]["c"]
        atr_val = atr(candles[idx-14:idx+1], 14)
        if atr_val is None or atr_val <= 0:
            continue
        
        trailing_stop = entry_price - (ATR_MULTIPLIER * atr_val)
        highest = entry_price
        position_size_usd = (equity * RISK_PER_TRADE_PCT) / (ATR_MULTIPLIER * atr_val) * entry_price
        if position_size_usd > equity:
            position_size_usd = equity
        
        exit_price = entry_price
        # Simulate forward until exit
        for j in range(idx + 1, min(idx + 200, len(candles))):
            price = candles[j]["c"]
            current_atr = atr(candles[j-14:j+1], 14)
            if current_atr is None:
                current_atr = atr_val
            
            if price > highest:
                highest = price
                new_stop = highest - (ATR_MULTIPLIER * current_atr)
                if new_stop > trailing_stop:
                    trailing_stop = new_stop
            
            if price <= trailing_stop:
                exit_price = trailing_stop
                break
            exit_price = price
        
        gross = (exit_price - entry_price) / entry_price
        net = gross - fee_rate
        pnl_usd = position_size_usd * net
        equity += pnl_usd
        trades.append(net)
    
    return trades


def main():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return
    
    with open(DATA_FILE, 'r') as f:
        candles = json.load(f)
    
    print(f"=== Monte Carlo Test: Momentum on BTCTMN ===")
    print(f"Total candles: {len(candles)}")
    print(f"Running actual strategy first...")
    
    actual_trades = run_actual_strategy(candles)
    if not actual_trades:
        print("No actual trades generated.")
        return
    
    actual_total = sum(actual_trades) * 100  # Sum of returns
    actual_wins = sum(1 for t in actual_trades if t > 0)
    actual_n = len(actual_trades)
    
    print(f"\n--- Actual Strategy ---")
    print(f"Trades: {actual_n}")
    print(f"Wins: {actual_wins} ({actual_wins/actual_n*100:.1f}%)")
    print(f"Total Return (sum): {actual_total:.2f}%")
    
    # Monte Carlo: 1000 simulations with random entries
    print(f"\nRunning Monte Carlo (1000 simulations with random entries)...")
    NUM_SIMULATIONS = 1000
    sim_returns = []
    rng = random.Random(42)
    
    for sim in range(NUM_SIMULATIONS):
        random_trades = run_random_strategy(candles, actual_n, rng)
        if random_trades:
            sim_returns.append(sum(random_trades) * 100)
        
        if (sim + 1) % 200 == 0:
            print(f"  {sim + 1}/{NUM_SIMULATIONS} simulations done...")
    
    if not sim_returns:
        print("Monte Carlo failed to generate simulations.")
        return
    
    sim_returns.sort()
    mean = sum(sim_returns) / len(sim_returns)
    p95 = sim_returns[int(len(sim_returns) * 0.95)]
    p99 = sim_returns[int(len(sim_returns) * 0.99)]
    better_than_actual = sum(1 for r in sim_returns if r >= actual_total)
    p_value = better_than_actual / len(sim_returns)
    
    print(f"\n=== Monte Carlo Results ===")
    print(f"Random Mean Return: {mean:.2f}%")
    print(f"95th Percentile of Random: {p95:.2f}%")
    print(f"99th Percentile of Random: {p99:.2f}%")
    print(f"P-Value (Probability of Luck): {p_value:.4f}")
    print(f"Simulations where Random >= Actual: {better_than_actual}/{len(sim_returns)}")
    
    print(f"\n--- Conclusion ---")
    if p_value < 0.05:
        print(f"✅ PASSED: Strategy's return is statistically significant (p < 0.05)")
        print(f"   Very unlikely to be due to random chance.")
    else:
        print(f"❌ FAILED: Strategy's return could be due to chance (p >= 0.05)")
        print(f"   Random entries with same exits performed as well or better.")
    
    print(f"\n--- Gate D-68-Plus (Monte Carlo) ---")
    print(f"P-Value < 0.05: {'PASS' if p_value < 0.05 else 'FAIL'} (p = {p_value:.4f})")


if __name__ == "__main__":
    main()
