import requests
import pandas as pd
import numpy as np
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

def main():
    print("Fetching ETH and BTC data...")
    df_eth = fetch_klines('ETHUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    
    if df_eth.empty or df_btc.empty:
        print("Data fetch failed.")
        return
        
    df_eth.rename(columns={'c': 'eth'}, inplace=True)
    df_btc.rename(columns={'c': 'btc'}, inplace=True)
    df = pd.merge(df_eth, df_btc, on='t').dropna().reset_index(drop=True)
    
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['eth_mom'] = (df['eth'] / df['eth'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    # --- 1. Run Actual Strategy ---
    equity = 1000.0
    in_position = False
    entry_price = 0
    entry_idx = 0
    hold_periods = 3
    fee_rate = 0.002
    actual_trades = 0
    
    for i in range(len(df)):
        if in_position:
            if i - entry_idx >= hold_periods:
                exit_price = df['eth'].iloc[i]
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                actual_trades += 1
                in_position = False
        else:
            if df['btc_mom'].iloc[i] > 0.02 and df['eth_mom'].iloc[i] < 0.005:
                in_position = True
                entry_price = df['eth'].iloc[i]
                entry_idx = i
                
    actual_return = ((equity - 1000.0) / 1000.0) * 100
    print(f"--- Actual Strategy ---")
    print(f"Total Trades: {actual_trades}")
    print(f"Actual Return: {actual_return:.2f}%\n")
    
    # --- 2. Monte Carlo Simulation (1000 random runs) ---
    print("Running Monte Carlo Permutation Test (1000 simulations)...")
    simulations = 1000
    random_returns = []
    
    # We generate random entry points for each simulation
    np.random.seed(42) # For reproducibility
    
    for _ in range(simulations):
        sim_equity = 1000.0
        # Randomly select start indices (ensuring they are within bounds and don't overlap if possible, 
        # but for simplicity of this permutation test, independent random trades are fine)
        random_indices = np.random.choice(range(len(df) - hold_periods), size=actual_trades, replace=False)
        
        for idx in random_indices:
            entry_p = df['eth'].iloc[idx]
            exit_p = df['eth'].iloc[idx + hold_periods]
            gross_ret = (exit_p - entry_p) / entry_p
            net_ret = gross_ret - fee_rate
            sim_equity += (sim_equity * net_ret)
            
        sim_return = ((sim_equity - 1000.0) / 1000.0) * 100
        random_returns.append(sim_return)
        
    random_returns = np.array(random_returns)
    
    # --- 3. Analyze Results ---
    better_than_actual = np.sum(random_returns >= actual_return)
    p_value = better_than_actual / simulations
    
    percentile_95 = np.percentile(random_returns, 95)
    percentile_99 = np.percentile(random_returns, 99)
    
    print(f"\n=== Monte Carlo Results ===")
    print(f"Random Mean Return: {np.mean(random_returns):.2f}%")
    print(f"95th Percentile of Random Returns: {percentile_95:.2f}%")
    print(f"99th Percentile of Random Returns: {percentile_99:.2f}%")
    print(f"P-Value (Probability of Luck): {p_value:.4f}")
    
    if p_value < 0.05:
        print("\nCONCLUSION: PASSED. The strategy's return is statistically significant (p < 0.05).")
        print("It is highly unlikely that this performance was due to random chance.")
    else:
        print("\nCONCLUSION: FAILED. The strategy's return can be explained by random chance (p >= 0.05).")

if __name__ == "__main__":
    main()
