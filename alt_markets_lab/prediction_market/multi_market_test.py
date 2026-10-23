import requests
import pandas as pd
import numpy as np
import json
import os
import math

# --- Reuse helpers from data_adapter ---
def fetch_markets(limit=200):
    url = f"https://gamma-api.polymarket.com/markets?limit={limit}&active=true&closed=false&order=volume24hr&ascending=false"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json() if isinstance(r.json(), list) else []
        return []
    except: return []

def get_token_ids(market):
    tokens = []
    clob = market.get('clobTokenIds')
    if clob:
        try:
            ids = json.loads(clob) if isinstance(clob, str) else clob
            if isinstance(ids, list): tokens.extend(ids)
        except: pass
    tok = market.get('tokens')
    if tok:
        try:
            if isinstance(tok, str): tok = json.loads(tok)
            if isinstance(tok, list):
                for t in tok:
                    if isinstance(t, dict) and t.get('token_id'):
                        tokens.append(t['token_id'])
        except: pass
    return list(set(tokens))

def fetch_price_history(token_id, interval='max', fidelity=60):
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity={fidelity}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict): return data.get("history", [])
            elif isinstance(data, list): return data
        return []
    except: return []

def to_candles(history):
    """Convert history to 4H candles DataFrame."""
    if len(history) < 20: return None
    df = pd.DataFrame(history)
    df['t'] = pd.to_datetime(df['t'], unit='s', utc=True)
    df.set_index('t', inplace=True)
    df.rename(columns={'p': 'close'}, inplace=True)
    resampled = df['close'].resample('4h').agg(['first', 'max', 'min', 'last'])
    resampled.columns = ['open', 'high', 'low', 'close']
    resampled['volume'] = 0
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled.rename(columns={'t': 'timestamp'}, inplace=True)
    return resampled

# --- Backtest logic (M9 Adapted) ---
def backtest_m9(candles, fee_rate=0.002):
    """Returns list of trade returns and equity curve for one market."""
    df = candles.copy()
    if len(df) < 50: return [], [1000.0]
    
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['lower_bb'] = df['sma20'] - 2 * df['std20']
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    in_position = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    trades = []
    equity_curve = [equity]
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        
        if in_position:
            if row['low'] <= sl_price:
                gross = (sl_price - entry_price) / entry_price
                net = gross - fee_rate
                equity += equity * net
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
            elif row['high'] >= tp_price:
                gross = (tp_price - entry_price) / entry_price
                net = gross - fee_rate
                equity += equity * net
                trades.append(net)
                equity_curve.append(equity)
                in_position = False
        else:
            if row['close'] <= row['lower_bb'] and row['rsi'] < 35 and row['close'] > 0.01:
                in_position = True
                entry_price = row['close']
                sl_price = entry_price * 0.98
                tp_price = entry_price * 1.04
    
    return trades, equity_curve

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denom

def main():
    os.makedirs("data", exist_ok=True)
    print("=== Multi-Market Test: M9 on Prediction Markets ===\n")
    
    print("Step 1: Fetching top markets...")
    markets = fetch_markets(limit=100)
    print(f"Received {len(markets)} markets.\n")
    
    print("Step 2: Running M9 on first 10 markets with valid data...")
    
    all_trades = []
    market_count = 0
    max_markets = 10
    
    for i, m in enumerate(markets[:30]):
        if market_count >= max_markets:
            break
        
        question = m.get('question', 'Unknown')[:70]
        token_ids = get_token_ids(m)
        if not token_ids:
            continue
        
        # Use first token (Yes)
        token_id = token_ids[0]
        history = fetch_price_history(token_id)
        
        if len(history) < 50:
            print(f"  [{i+1}] SKIP (only {len(history)} pts): {question}")
            continue
        
        candles = to_candles(history)
        if candles is None or len(candles) < 50:
            print(f"  [{i+1}] SKIP (not enough candles): {question}")
            continue
        
        trades, equity = backtest_m9(candles)
        
        if len(trades) > 0:
            all_trades.extend(trades)
            net_pnl = (equity[-1] - 1000) / 1000 * 100
            print(f"  [{i+1}] ✓ {question}")
            print(f"       Trades: {len(trades)} | PnL: {net_pnl:.2f}% | Final Eq: ${equity[-1]:.2f}")
            market_count += 1
        else:
            print(f"  [{i+1}] NO TRADES: {question}")
    
    print(f"\n=== Aggregated Results (All Markets) ===")
    if not all_trades:
        print("No trades across all markets.")
        return
    
    trades = np.array(all_trades)
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    win_count = len(wins)
    total = len(trades)
    
    # Compound equity across all trades
    equity = 1000.0
    equity_curve = [equity]
    for t in trades:
        equity += equity * t
        equity_curve.append(equity)
    
    net_pnl = ((equity - 1000) / 1000) * 100
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    win_rate = win_count / total
    expectancy = (win_rate * (avg_win / 0.01)) - ((1 - win_rate) * (avg_loss / 0.01))
    
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
    
    wilson = calculate_wilson_lower(win_count, total) * 100
    
    print(f"Markets Analyzed: {market_count}")
    print(f"Total Trades: {total}")
    print(f"Wins: {win_count} | Losses: {total - win_count}")
    print(f"Win Rate: {win_rate*100:.1f}%")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Final Equity: ${equity:.2f}")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R")
    print(f"Max Drawdown: {max_dd*100:.2f}%")
    print(f"Wilson Lower Bound: {wilson:.2f}%")
    
    print(f"\n--- Gate D-68-Plus Check ---")
    print(f"n >= 30:         {'PASS' if total >= 30 else 'FAIL'} ({total})")
    print(f"PF > 1.2:        {'PASS' if pf > 1.2 else 'FAIL'} ({pf:.2f})")
    print(f"Expectancy>0.1R: {'PASS' if expectancy > 0.1 else 'FAIL'} ({expectancy:.3f})")
    print(f"MaxDD < 15%:     {'PASS' if max_dd*100 < 15 else 'FAIL'} ({max_dd*100:.2f}%)")
    print(f"Wilson > 36%:    {'PASS' if wilson > 36 else 'FAIL'} ({wilson:.2f}%)")

if __name__ == "__main__":
    main()
