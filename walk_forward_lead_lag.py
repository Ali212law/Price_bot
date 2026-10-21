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
    return pd.DataFrame(sorted(list(unique.values()), key=lambda x: x['t']))

def calculate_metrics(trades, equity_curve):
    if len(trades) == 0:
        return 0, 0, 0, 0, 0
        
    trades = np.array(trades)
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    
    win_count = len(wins)
    total_trades = len(trades)
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    
    net_pnl = ((equity_curve[-1] - 1000.0) / 1000.0) * 100
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
        
    return total_trades, net_pnl, pf, expectancy, max_dd * 100

def run_backtest(df_slice, symbol='ETHUSDT'):
    lookback = 14
    df = df_slice.copy()
    df['target_mom'] = (df['target'] / df['target'].shift(lookback)) - 1
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    if len(df) < 10: return [], [1000.0]
    
    equity = 1000.0
    in_position = False
    entry_price = 0
    entry_idx = 0
    hold_periods = 3
    fee_rate = 0.002
    
    trades = []
    equity_curve = [equity]
    
    for i in range(len(df)):
        if in_position:
            if i - entry_idx >= hold_periods:
                exit_price = df['target'].iloc[i]
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
        else:
            if df['btc_mom'].iloc[i] > 0.02 and df['target_mom'].iloc[i] < 0.005:
                in_position = True
                entry_price = df['target'].iloc[i]
                entry_idx = i
                
    return trades, equity_curve

def main():
    print("Fetching ETH and BTC data (2 Years)...")
    df_eth = fetch_klines('ETHUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    
    if df_eth.empty or df_btc.empty:
        print("Data fetch failed.")
        return
        
    df_eth.rename(columns={'c': 'target'}, inplace=True)
    df_btc.rename(columns={'c': 'btc'}, inplace=True)
    
    df = pd.merge(df_eth, df_btc, on='t').dropna().reset_index(drop=True)
    
    # Split into 4 equal chunks (approx 6 months each)
    chunk_size = len(df) // 4
    
    print("=== Walk-Forward Analysis (Regime Stability) for Lead-Lag ===")
    print("Parameters are LOCKED. Testing stability across 4 sequential time windows.\n")
    
    for i in range(4):
        start_idx = i * chunk_size
        end_idx = (i + 1) * chunk_size if i < 3 else len(df)
        
        window_df = df.iloc[start_idx:end_idx]
        start_date = pd.to_datetime(window_df['t'].iloc[0], unit='ms').strftime('%Y-%m-%d')
        end_date = pd.to_datetime(window_df['t'].iloc[-1], unit='ms').strftime('%Y-%m-%d')
        
        trades, equity_curve = run_backtest(window_df)
        n, pnl, pf, exp, dd = calculate_metrics(trades, equity_curve)
        
        print(f"--- Window {i+1} ({start_date} to {end_date}) ---")
        print(f"Trades: {n} | Net PnL: {pnl:.2f}% | PF: {pf:.2f} | Exp: {exp:.3f}R | MaxDD: {dd:.2f}%")
        
        if n < 5:
            print("Note: Too few trades in this window to be statistically meaningful.")
        print("")

if __name__ == "__main__":
    main()
