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
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])
                    })
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    return pd.DataFrame(sorted(list(unique.values()), key=lambda x: x['t']))

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def backtest_msb(df, symbol):
    lookback = 20
    df['high_max'] = df['h'].rolling(window=lookback).max().shift(1)
    df['low_min'] = df['l'].rolling(window=lookback).min().shift(1)
    df['vol_sma'] = df['v'].rolling(window=lookback).mean().shift(1)
    
    # ATR
    df['tr'] = np.maximum(df['h'] - df['l'], np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    in_position = False
    entry_price = 0
    sl_price = 0
    pos_size = 0
    
    trades = []
    equity_curve = [equity]
    fee_rate = 0.001
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        
        if in_position:
            # Check SL (using low for long)
            if row['l'] <= sl_price:
                exit_price = sl_price
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (pos_size * (exit_price - entry_price)) - (pos_size * entry_price * 2 * fee_rate)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
            # Check Trend Reversal (Close below 20-period low)
            elif row['c'] < row['low_min']:
                exit_price = row['c']
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (pos_size * (exit_price - entry_price)) - (pos_size * entry_price * 2 * fee_rate)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
        else:
            # Entry Condition: Close > 20-period High AND Volume > 1.5x Avg Vol
            if row['c'] > row['high_max'] and row['v'] > (1.5 * row['vol_sma']):
                in_position = True
                entry_price = row['c']
                sl_price = entry_price - (2 * row['atr'])
                
                risk_per_unit = entry_price - sl_price
                if risk_per_unit <= 0: 
                    in_position = False
                    continue
                    
                risk_amount = equity * 0.005 # 0.5% Risk
                pos_size = risk_amount / risk_per_unit
                
                # Cap position size to 1x equity
                cost = pos_size * entry_price
                if cost > equity:
                    pos_size = equity / entry_price

    total_trades = len(trades)
    if total_trades == 0:
        print(f"--- {symbol} ---\nNo trades generated.\n")
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
    
    print(f"--- {symbol} ---")
    print(f"Total Trades: {total_trades} | Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"Net PnL: {net_pnl:.2f}% | PF: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R | MaxDD: {max_dd*100:.2f}%")
    print(f"Wilson: {wilson_lower:.2f}% | Top 5 Concentration: {top_5_concentration:.1f}%\n")

if __name__ == "__main__":
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    print("=== Backtest of MSB (Market Structure Break) ===")
    print("Parameters: Lookback=20, Vol Filter=1.5x, SL=2 ATR\n")
    for sym in symbols:
        df = fetch_klines(sym, '4h', 730)
        if not df.empty:
            backtest_msb(df, sym)
