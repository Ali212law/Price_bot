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

def run_grid_backtest(df, btc_daily):
    """Returns the list of trade returns from the actual strategy."""
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['t'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill()
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    trades = []
    fee_rate = 0.001
    
    in_position = False
    levels = 0
    total_invested = 0.0
    total_units = 0.0
    initial_entry_price = 0.0
    
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
                in_position = False
                continue
                
            if current_price >= avg_entry_price * 1.02:
                gross_return = (current_price - avg_entry_price) / avg_entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (total_invested * net_return)
                trades.append(net_return)
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
                
    return trades

def monte_carlo_permutation(trades, n_simulations=1000):
    """Shuffles the trade returns to create a null distribution."""
    trades = np.array(trades)
    actual_return = np.sum(trades)
    
    sim_returns = []
    np.random.seed(42)
    for _ in range(n_simulations):
        # Shuffle the order (or just sample with replacement from the same distribution)
        sim_trades = np.random.choice(trades, size=len(trades), replace=True)
        sim_returns.append(np.sum(sim_trades))
        
    sim_returns = np.array(sim_returns)
    better = np.sum(sim_returns >= actual_return)
    p_value = better / n_simulations
    return actual_return, p_value, np.percentile(sim_returns, 95), np.percentile(sim_returns, 99)

def main():
    print("Fetching data for Safe Grid Monte Carlo...")
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    if btc_daily.empty:
        print("Data fetch failed.")
        return
        
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    for sym in symbols:
        df = fetch_klines(sym, '4h', 730)
        if df.empty: continue
        
        trades = run_grid_backtest(df, btc_daily)
        if not trades:
            print(f"--- {sym} --- No trades generated.")
            continue
            
        actual_ret, p_val, p95, p99 = monte_carlo_permutation(trades, 1000)
        
        print(f"--- {sym} ---")
        print(f"Actual Total Return: {actual_ret * 100:.2f}%")
        print(f"95th Percentile of Random: {p95 * 100:.2f}%")
        print(f"99th Percentile of Random: {p99 * 100:.2f}%")
        print(f"P-Value: {p_val:.4f}")
        
        if p_val < 0.05:
            print("CONCLUSION: PASSED. The strategy's return is statistically significant.\n")
        else:
            print("CONCLUSION: FAILED. The return could be due to chance.\n")

if __name__ == "__main__":
    main()
