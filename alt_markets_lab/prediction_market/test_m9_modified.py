import pandas as pd
import numpy as np
import math

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def backtest_m9_modified(csv_file):
    df = pd.read_csv(csv_file)
    if len(df) < 50:
        print("Not enough data.")
        return
    
    # Indicators
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
    
    fee_rate = 0.002  # 0.2% fee
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        
        if in_position:
            if row['low'] <= sl_price:
                # Hit SL
                gross_return = (sl_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                trades.append(net_return)
                in_position = False
            elif row['high'] >= tp_price:
                # Hit TP
                gross_return = (tp_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                trades.append(net_return)
                in_position = False
        else:
            # Entry: price below lower BB and RSI < 35
            if row['close'] <= row['lower_bb'] and row['rsi'] < 35:
                in_position = True
                entry_price = row['close']
                sl_price = entry_price * 0.98  # 2% SL
                tp_price = entry_price * 1.04  # 4% TP
    
    if not trades:
        print("No trades generated.")
        return
    
    trades = np.array(trades)
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    
    win_count = len(wins)
    total = len(trades)
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    
    net_pnl = ((equity - 1000.0) / 1000.0) * 100
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    win_rate = win_count / total
    expectancy = (win_rate * (avg_win/0.01)) - ((1 - win_rate) * (avg_loss/0.01))
    
    wilson = calculate_wilson_lower(win_count, total) * 100
    
    print(f"=== Results for {csv_file} ===")
    print(f"Total Trades: {total}")
    print(f"Win Rate: {win_rate*100:.1f}%")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R")
    print(f"Wilson Lower Bound: {wilson:.2f}%")

if __name__ == "__main__":
    # Example usage: run after data_adapter has saved a CSV
    import os
    # Find the first CSV in data folder
    data_dir = "data"
    if os.path.exists(data_dir):
        files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        if files:
            backtest_m9_modified(os.path.join(data_dir, files[0]))
        else:
            print("No CSV files found. Run data_adapter.py first.")
    else:
        print("Data directory not found.")
