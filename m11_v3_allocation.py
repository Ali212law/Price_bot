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

def main():
    print("Fetching Data for M11-V3 (M9 + LL + Filtered Donchian)...")
    df_target = fetch_klines('ETHUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    
    if df_target.empty or df_btc.empty: return
    
    # --- Indicators ---
    # M9 (BB, RSI, ATR)
    df_target['sma20'] = df_target['c'].rolling(20).mean()
    df_target['std20'] = df_target['c'].rolling(20).std()
    df_target['lower_bb'] = df_target['sma20'] - (2 * df_target['std20'])
    delta = df_target['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df_target['rsi'] = 100 - (100 / (1 + (gain/loss)))
    df_target['tr'] = np.maximum(df_target['h'] - df_target['l'], np.maximum(abs(df_target['h'] - df_target['c'].shift(1)), abs(df_target['l'] - df_target['c'].shift(1))))
    df_target['atr'] = df_target['tr'].rolling(14).mean()
    
    # Donchian (50-period) + Volume Filter
    df_target['high_50'] = df_target['h'].rolling(50).max().shift(1)
    df_target['low_50'] = df_target['l'].rolling(50).min().shift(1)
    df_target['vol_sma'] = df_target['v'].rolling(50).mean().shift(1)
    
    df_target.rename(columns={'c': 'target', 't': 'time'}, inplace=True)
    df_btc.rename(columns={'c': 'btc', 't': 'time'}, inplace=True)
    
    df = pd.merge(df_target[['time', 'target', 'sma20', 'lower_bb', 'rsi', 'atr', 'high_50', 'low_50', 'vol_sma', 'v']], df_btc[['time', 'btc']], on='time').dropna()
    
    # ADX Merge
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['time'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill().dropna()
    
    # Momentum for LL
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['target_mom'] = (df['target'] / df['target'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    # --- Engine Setup ---
    equity = 1000.0
    equity_curve = [equity]
    fee_rate = 0.002
    trades = []
    
    current_regime = "NEUTRAL"
    positions = {} # {strategy: {'entry': price, 'time': idx, 'sl': price, 'weight': w}}
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        adx = row['adx']
        
        # 1. Regime Detection
        if adx > 25: current_regime = "TREND"
        elif adx < 20: current_regime = "RANGE"
        
        # 2. Weights Assignment
        if current_regime == "TREND":
            w_ll, w_don, w_m9 = 0.4, 0.4, 0.2
        elif current_regime == "RANGE":
            w_m9, w_ll, w_don = 0.6, 0.2, 0.2
        else:
            w_m9, w_ll, w_don = 0.333, 0.333, 0.334
            
        # 3. Manage Exits
        for strat, pos in list(positions.items()):
            exit_triggered = False
            exit_price = row['target']
            
            if strat == "M9":
                if row['target'] >= row['sma20'] or row['target'] <= pos['sl']:
                    exit_triggered = True
            elif strat == "LL":
                if i - pos['time'] >= 3:
                    exit_triggered = True
            elif strat == "DON":
                if row['target'] <= row['low_50'] or row['target'] <= pos['sl']:
                    exit_triggered = True
                    
            if exit_triggered:
                gross_ret = (exit_price - pos['entry']) / pos['entry']
                net_ret = gross_ret - fee_rate
                equity += (equity * net_ret * pos['weight'])
                trades.append(net_ret)
                del positions[strat]

        # 4. Manage Entries
        # M9
        if "M9" not in positions:
            if row['target'] <= row['lower_bb'] and row['rsi'] < 35:
                positions["M9"] = {'entry': row['target'], 'sl': row['target'] - (2*row['atr']), 'time': i, 'weight': w_m9}
                
        # LL
        if "LL" not in positions:
            if row['btc_mom'] > 0.02 and row['target_mom'] < 0.005:
                positions["LL"] = {'entry': row['target'], 'sl': 0, 'time': i, 'weight': w_ll}
                
        # Filtered Donchian
        if "DON" not in positions:
            if row['target'] > row['high_50'] and row['v'] > (1.5 * row['vol_sma']):
                positions["DON"] = {'entry': row['target'], 'sl': row['target'] - (2*row['atr']), 'time': i, 'weight': w_don}
                
        equity_curve.append(equity)

    # Metrics
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades generated.")
        return
        
    net_pnl = ((equity - 1000.0) / 1000.0) * 100
    peak = max(equity_curve)
    max_dd = max([(peak - eq) / peak for eq in equity_curve]) * 100
    
    print("=== M11-V3 Allocation Engine (M9 + LL + Filtered Donchian) ===")
    print(f"Final Equity: ${equity:.2f}")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Total Trades (Closed): {total_trades}")

if __name__ == "__main__":
    main()
