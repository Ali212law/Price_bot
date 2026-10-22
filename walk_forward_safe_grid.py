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
    return pd.DataFrame(sorted(list(unique.values()), key=lambda x: x['t']))

def calculate_daily_adx(btc_daily):
    df = btc_daily.copy()
    df['tr'] = np.maximum(df['h'] - df['l'], np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['up'] = df['h'] - df['h'].shift(1)
    df['down'] = df['l'].shift(1) - df['l']
    df['+dm'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0.0)
    df['-dm'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0.0)
    period = 14
    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    df['+di'] = 100 * (df['+dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'])
    df['-di'] = 100 * (df['-dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'])
    df['dx'] = 100 * abs(df['+di'] - df['-di']) / (df['+di'] + df['-di'])
    df['adx'] = df['dx'].ewm(alpha=1/period, adjust=False).mean()
    return df[['t', 'adx']]

def run_grid_backtest(df_slice):
    if len(df_slice) < 20: return [], [1000.0]
    
    equity = 1000.0
    trades = []
    equity_curve = [equity]
    fee_rate = 0.001
    
    in_position = False
    levels = 0
    total_invested = 0.0
    total_units = 0.0
    initial_entry_price = 0.0
    
    df = df_slice.reset_index(drop=True)
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        adx = row['adx']
        current_price = row['c']
        
        if in_position:
            avg_entry_price = total_invested / total_units
            
            if current_price <= initial_entry_price * 0.90:
                gross_return = (current_price - avg_entry_price) / avg_entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (total_invested * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                continue
                
            if current_price >= avg_entry_price * 1.02:
                gross_return = (current_price - avg_entry_price) / avg_entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (total_invested * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                continue
                
            if levels == 1 and current_price <= initial_entry_price * 0.97:
                amount = (equity * 0.005) / 0.03
                amount = min(amount, equity / 3)
                total_units += amount / current_price
                total_invested += amount
                levels = 2
            elif levels == 2 and current_price <= initial_entry_price * 0.94:
                amount = (equity * 0.005) / 0.06
                amount = min(amount, equity / 3)
                total_units += amount / current_price
                total_invested += amount
                levels = 3
        else:
            if adx < 20:
                in_position = True
                levels = 1
                initial_entry_price = current_price
                amount = equity / 3
                total_units = amount / current_price
                total_invested = amount
                
    return trades, equity_curve

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

def main():
    print("Fetching Data for Safe Grid Walk-Forward Analysis...")
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    if btc_daily.empty:
        print("BTC data fetch failed.")
        return
        
    daily_adx = calculate_daily_adx(btc_daily)
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    
    for sym in symbols:
        print(f"\n=== Walk-Forward Analysis for {sym} ===")
        df = fetch_klines(sym, '4h', 730)
        if df.empty: continue
        
        df['date'] = pd.to_datetime(df['t'], unit='ms').dt.date
        df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill().dropna().reset_index(drop=True)
        
        # Split into 4 windows
        chunk_size = len(df) // 4
        
        for i in range(4):
            start_idx = i * chunk_size
            end_idx = (i + 1) * chunk_size if i < 3 else len(df)
            window_df = df.iloc[start_idx:end_idx]
            
            start_date = pd.to_datetime(window_df['t'].iloc[0], unit='ms').strftime('%Y-%m-%d')
            end_date = pd.to_datetime(window_df['t'].iloc[-1], unit='ms').strftime('%Y-%m-%d')
            
            trades, equity_curve = run_grid_backtest(window_df)
            n, pnl, pf, exp, dd = calculate_metrics(trades, equity_curve)
            
            print(f"--- Window {i+1} ({start_date} to {end_date}) ---")
            print(f"Trades: {n} | Net PnL: {pnl:.2f}% | PF: {pf:.2f} | Exp: {exp:.3f}R | MaxDD: {dd:.2f}%")
            
            if n < 5 and n > 0:
                print("Note: Low trade count in this window.")

if __name__ == "__main__":
    main()
