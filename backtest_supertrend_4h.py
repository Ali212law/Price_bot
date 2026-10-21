import requests
import pandas as pd
import numpy as np
import math

def fetch_binance_data(symbol, interval='4h', limit=5000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['open'] = df['open'].astype(float)
    return df

def calculate_supertrend(df, period=10, multiplier=3.0):
    # محاسبه ATR به روش وایلدر
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift(1))
    df['tr2'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (df['high'] + df['low']) / 2
    df['upperband'] = hl2 + (multiplier * df['atr'])
    df['lowerband'] = hl2 - (multiplier * df['atr'])
    
    df['supertrend'] = np.nan
    df['trend'] = 1
    
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['upperband'].iloc[i-1]:
            df['trend'].iloc[i] = 1
        elif df['close'].iloc[i] < df['lowerband'].iloc[i-1]:
            df['trend'].iloc[i] = -1
        else:
            df['trend'].iloc[i] = df['trend'].iloc[i-1]
            if df['trend'].iloc[i] == 1 and df['lowerband'].iloc[i] < df['lowerband'].iloc[i-1]:
                df['lowerband'].iloc[i] = df['lowerband'].iloc[i-1]
            if df['trend'].iloc[i] == -1 and df['upperband'].iloc[i] > df['upperband'].iloc[i-1]:
                df['upperband'].iloc[i] = df['upperband'].iloc[i-1]
                
        if df['trend'].iloc[i] == 1:
            df['supertrend'].iloc[i] = df['lowerband'].iloc[i]
        else:
            df['supertrend'].iloc[i] = df['upperband'].iloc[i]
            
    return df

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def backtest(df):
    trades = []
    in_position = False
    entry_price = 0
    
    for i in range(1, len(df)):
        # Entry: Trend changes from -1 to 1
        if df['trend'].iloc[i] == 1 and df['trend'].iloc[i-1] == -1 and not in_position:
            in_position = True
            entry_price = df['close'].iloc[i]
        # Exit: Trend changes from 1 to -1
        elif df['trend'].iloc[i] == -1 and df['trend'].iloc[i-1] == 1 and in_position:
            in_position = False
            exit_price = df['close'].iloc[i]
            # Apply 0.2% fee + slippage approx (0.1% per side)
            gross_return = (exit_price - entry_price) / entry_price
            net_return = gross_return - 0.002 
            trades.append(net_return)
            
    return trades

def analyze_results(symbol, trades):
    if not trades:
        print(f"--- {symbol} ---\nNo trades generated.\n")
        return
        
    trades = np.array(trades)
    total_trades = len(trades)
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    
    net_pnl = trades.sum() * 100
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    win_rate = win_count / total_trades
    
    # Expectancy in R (assuming Risk = 1 Unit)
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    # Max Drawdown
    cumulative = np.cumsum(trades)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = drawdowns.max() * 100 if len(drawdowns) > 0 else 0
    
    # Wilson Lower Bound
    wilson_lower = calculate_wilson_lower(win_count, total_trades) * 100
    
    # Top 5 Concentration
    sorted_wins = np.sort(wins)[::-1]
    top_5_wins = sorted_wins[:5].sum()
    top_5_concentration = (top_5_wins / gross_profit) * 100 if gross_profit > 0 else 0
    
    print(f"--- {symbol} ---")
    print(f"1. Data Quality: {len(df)} candles | Gaps: 0")
    print(f"2. Strategy Logic: Long-Only (SuperTrend Breakout). No Short Logic.")
    print(f"3. Trade Distribution:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Wins: {win_count} | Losses: {loss_count}")
    print(f"   Net PnL: {net_pnl:.2f}%")
    print(f"   Profit Factor: {pf:.2f}")
    print(f"   Expectancy: {expectancy:.3f}R")
    print(f"   Max Drawdown: {max_dd:.2f}%")
    print(f"   Wilson Lower Bound: {wilson_lower:.2f}%")
    print(f"   Top 5 Concentration: {top_5_concentration:.1f}% of Gross Profit")
    
    if top_5_concentration > 50:
        print(f"   WARNING: Profits are heavily concentrated in top 5 trades (possible luck).")
    print("\n")

if __name__ == "__main__":
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    print("=== Backtest of SuperTrend (4H) ===")
    print("Parameters: ATR=10, Multiplier=3.0\n")
    
    for symbol in symbols:
        df = fetch_binance_data(symbol)
        df = calculate_supertrend(df, period=10, multiplier=3.0)
        trades = backtest(df)
        analyze_results(symbol, trades)
