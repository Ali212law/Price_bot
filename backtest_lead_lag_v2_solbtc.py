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
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])
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
    print("Fetching SOL and BTC data (Out-of-Sample Test for V2)...")
    df_sol = fetch_klines('SOLUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    
    if df_sol.empty or df_btc.empty:
        print("Data fetch failed.")
        return
        
    df_sol.rename(columns={'c': 'sol', 'h': 'high', 'l': 'low'}, inplace=True)
    df_btc.rename(columns={'c': 'btc', 'h': 'high', 'l': 'low'}, inplace=True)
    
    df = pd.merge(df_sol, df_btc, on='t', suffixes=('_sol', '_btc')).dropna()
    
    # 14-period momentum
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['sol_mom'] = (df['sol'] / df['sol'].shift(lookback)) - 1
    df['sol_mom_3'] = (df['sol'] / df['sol'].shift(3)) - 1
    
    # BTC ATR(14)
    df['tr'] = np.maximum(df['high_btc'] - df['low_btc'], 
                          np.maximum(abs(df['high_btc'] - df['btc'].shift(1)), 
                                     abs(df['low_btc'] - df['btc'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    in_position = False
    entry_price = 0
    entry_idx = 0
    hold_periods = 3
    
    trades = []
    equity_curve = [equity]
    fee_rate = 0.002 
    
    for i in range(len(df)):
        if in_position:
            # Hybrid Exit: Time-based OR momentum-based
            time_exit = (i - entry_idx) >= hold_periods
            mom_exit = df['sol_mom_3'].iloc[i] > 0.02
            
            if time_exit or mom_exit:
                exit_price = df['sol'].iloc[i]
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
        else:
            # Entry condition with ATR filter
            btc_pump = df['btc_mom'].iloc[i] > 0.02
            sol_lags = df['sol_mom'].iloc[i] < 0.005
            strong_candle = (df['btc'].iloc[i] - df['btc'].iloc[i-1]) > (1.5 * df['atr'].iloc[i])
            
            if btc_pump and sol_lags and strong_candle:
                in_position = True
                entry_price = df['sol'].iloc[i]
                entry_idx = i

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
    
    print("=== Backtest of Lead-Lag V2 (SOL/BTC) ===")
    print("Logic: ATR Filter + Hybrid Exit (Time/Momentum)\n")
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
