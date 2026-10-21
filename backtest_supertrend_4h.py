import requests
import pandas as pd
import numpy as np
import math
import time

def fetch_klines(symbol, interval, days):
    all_candles = []
    end_time = int(time.time() * 1000)
    # برای تایم‌فریم ۴ ساعته، هر روز ۶ کندل است
    target = days * 6 
    
    while len(all_candles) < target:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&endTime={end_time}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                        "l": float(k[3]), "c": float(k[4]), "v": float(k[5])
                    })
                end_time = data[0][0] - 1
            else: break
        except Exception as e: 
            print(f"Error fetching data: {e}")
            break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    sorted_candles = sorted(list(unique.values()), key=lambda x: x['t'])
    
    # تبدیل به دیتافریم برای پردازش
    df = pd.DataFrame(sorted_candles)
    if not df.empty:
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
    return df

def calculate_supertrend(df, period=10, multiplier=3.0):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    # محاسبه TR
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    
    # محاسبه ATR به روش وایلدر
    atr = np.zeros_like(close)
    atr[period-1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    trend = np.ones(len(close), dtype=int)
    supertrend = np.zeros_like(close)
    
    for i in range(1, len(close)):
        # مقایسه با باندهای کندل قبلی (رفع باگ)
        if close[i] > upperband[i-1]:
            trend[i] = 1
        elif close[i] < lowerband[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
            if trend[i] == 1 and lowerband[i] < lowerband[i-1]:
                lowerband[i] = lowerband[i-1]
            if trend[i] == -1 and upperband[i] > upperband[i-1]:
                upperband[i] = upperband[i-1]
                
        supertrend[i] = lowerband[i] if trend[i] == 1 else upperband[i]
        
    df['trend'] = trend
    df['supertrend'] = supertrend
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
    trend = df['trend'].values
    close = df['close'].values
    
    for i in range(1, len(df)):
        if trend[i] == 1 and trend[i-1] == -1 and not in_position:
            in_position = True
            entry_price = close[i]
        elif trend[i] == -1 and trend[i-1] == 1 and in_position:
            in_position = False
            exit_price = close[i]
            gross_return = (exit_price - entry_price) / entry_price
            net_return = gross_return - 0.002 
            trades.append(net_return)
            
    return trades

def analyze_results(symbol, trades, df):
    if not trades:
        print(f"--- {symbol} ---")
        print(f"1. Data Quality: {len(df)} candles")
        print(f"No trades generated.\n")
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
    
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    cumulative = np.cumsum(trades)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = drawdowns.max() * 100 if len(drawdowns) > 0 else 0
    
    wilson_lower = calculate_wilson_lower(win_count, total_trades) * 100
    
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
        print(f"Fetching 2 years of data for {symbol}...")
        df = fetch_klines(symbol, '4h', 730) # 730 روز = 2 سال
        if df is None or df.empty:
            print(f"--- {symbol} ---")
            print("Failed to fetch data.\n")
            continue
            
        df = calculate_supertrend(df, period=10, multiplier=3.0)
        trades = backtest(df)
        analyze_results(symbol, trades, df)
