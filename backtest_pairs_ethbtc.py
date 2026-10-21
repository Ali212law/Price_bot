import requests
import pandas as pd
import numpy as np
import math
import time

def fetch_klines(symbol, interval, days):
    all_candles = []
    end_time = int(time.time() * 1000)
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
                        "t": int(k[0]), "c": float(k[4])
                    })
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    sorted_candles = sorted(list(unique.values()), key=lambda x: x['t'])
    return pd.DataFrame(sorted_candles)

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def main():
    print("Fetching ETH and BTC data...")
    df_eth = fetch_klines('ETHUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    
    if df_eth.empty or df_btc.empty:
        print("Data fetch failed.")
        return
        
    df_eth.rename(columns={'c': 'eth'}, inplace=True)
    df_btc.rename(columns={'c': 'btc'}, inplace=True)
    
    df = pd.merge(df_eth, df_btc, on='t').dropna()
    df['ratio'] = df['eth'] / df['btc']
    
    lookback = 30
    df['mean'] = df['ratio'].rolling(window=lookback).mean()
    df['std'] = df['ratio'].rolling(window=lookback).std()
    df['z_score'] = (df['ratio'] - df['mean']) / df['std']
    
    # Pre-condition: Half-life of Mean Reversion (Ornstein-Uhlenbeck)
    df['lag_ratio'] = df['ratio'].shift(1)
    df['delta_ratio'] = df['ratio'] - df['lag_ratio']
    df_hl = df.dropna().copy()
    
    x = df_hl['lag_ratio'].values
    y = df_hl['delta_ratio'].values
    A = np.vstack([x, np.ones(len(x))]).T
    m, c = np.linalg.lstsq(A, y, rcond=None)[0]
    
    if m >= 0:
        print("Half-life calculation failed: Ratio is not mean-reverting (m >= 0).")
        return
        
    half_life = -np.log(2) / m
    print(f"=== Pre-condition: Half-life of Mean Reversion ===")
    print(f"Half-life: {half_life:.2f} periods (4H candles)")
    print(f"Estimated time to revert: {half_life * 4:.2f} hours\n")
    
    df = df.dropna()
    
    equity = 1000.0
    current_asset = 'BTC' 
    entry_eth = df['eth'].iloc[0]
    entry_btc = df['btc'].iloc[0]
    
    trades = []
    equity_curve = [equity]
    fee_rate = 0.001 # 0.1% per leg
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        z = row['z_score']
        
        target_asset = current_asset
        if z > 2:
            target_asset = 'BTC'
        elif z < -2:
            target_asset = 'ETH'
            
        if target_asset != current_asset:
            if current_asset == 'ETH':
                exit_price = row['eth']
                gross_return = (exit_price - entry_eth) / entry_eth
            else:
                exit_price = row['btc']
                gross_return = (exit_price - entry_btc) / entry_btc
                
            net_return = gross_return - fee_rate
            equity += (equity * net_return)
            trades.append(net_return)
            equity_curve.append(equity)
            
            current_asset = target_asset
            if current_asset == 'ETH':
                entry_eth = row['eth']
            else:
                entry_btc = row['btc']
                
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades generated.")
        return
        
    trades = np.array(trades)
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    
    win_count = len(wins)
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    
    net_pnl = (equity - 1000.0) / 1000.0 * 100
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    win_rate = win_count / total_trades
    expectancy = (win_rate * (avg_win/0.01)) - ((1 - win_rate) * (avg_loss/0.01))
    
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
        
    wilson_lower = calculate_wilson_lower(win_count, total_trades) * 100
    sorted_wins = np.sort(wins)[::-1]
    top_5_concentration = (sorted_wins[:5].sum() / gross_profit) * 100 if gross_profit > 0 else 0
    
    print("=== Backtest of Pairs Trading (ETH/BTC) ===")
    print("Logic: Long-Long Rotation (Z-score > 2 -> BTC, Z-score < -2 -> ETH)\n")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R")
    print(f"Max Drawdown: {max_dd*100:.2f}%")
    print(f"Wilson Lower Bound: {wilson_lower:.2f}%")
    print(f"Top 5 Concentration: {top_5_concentration:.1f}% of Gross Profit")

if __name__ == "__main__":
    main()
