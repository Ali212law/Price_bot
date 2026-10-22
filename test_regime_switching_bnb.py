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

def calculate_indicators(df):
    # RSI(14) & Bollinger Bands(20, 2) for Range Strategy (M9 logic)
    df['sma20'] = df['c'].rolling(window=20).mean()
    df['std20'] = df['c'].rolling(window=20).std()
    df['lower_bb'] = df['sma20'] - (2 * df['std20'])
    
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df

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
    print("Fetching BNB (Target) and BTC (Leader) Data...")
    df_bnb = fetch_klines('BNBUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    
    if df_bnb.empty or df_btc.empty or btc_daily.empty:
        print("Data fetch failed.")
        return
        
    df_bnb = calculate_indicators(df_bnb)
    df_bnb.rename(columns={'c': 'target', 't': 'time'}, inplace=True)
    df_btc.rename(columns={'c': 'btc', 't': 'time'}, inplace=True)
    
    # FIX: Added 'sma20' to the list of columns being merged
    df = pd.merge(df_bnb[['time', 'target', 'lower_bb', 'rsi', 'sma20']], df_btc[['time', 'btc']], on='time').dropna()
    
    # Calculate daily ADX and merge (Out-of-Sample for BNB)
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['time'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill().dropna()
    
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['target_mom'] = (df['target'] / df['target'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    # Backtest Engine
    equity = 1000.0
    in_position = False
    entry_price = 0
    strategy_mode = "NONE"
    hold_time = 0
    trades = []
    equity_curve = [equity]
    fee_rate = 0.002
    
    current_regime = "NEUTRAL" # State for Hysteresis
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        adx = row['adx']
        
        # Regime Detection (Hysteresis)
        if adx > 25:
            current_regime = "TREND"
        elif adx < 20:
            current_regime = "RANGE"
        # If 20 <= ADX <= 25, keep previous regime (Neutral acts as buffer)
        
        if in_position:
            hold_time += 1
            exit_signal = False
            
            # Exit Rules
            if strategy_mode == "LEAD_LAG":
                if hold_time >= 3: exit_signal = True
            elif strategy_mode == "RANGE_M9":
                if row['target'] > row['sma20'] or hold_time >= 10: 
                    # Simple exit for M9: hit middle BB or time stop
                    exit_signal = True
            
            if exit_signal:
                gross_return = (row['target'] - entry_price) / entry_price
                net_return = gross_return - fee_rate
                equity += (equity * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                strategy_mode = "NONE"
        else:
            # Entry Rules
            if current_regime == "TREND":
                # Lead-Lag Logic
                if row['btc_mom'] > 0.02 and row['target_mom'] < 0.005:
                    in_position = True
                    entry_price = row['target']
                    strategy_mode = "LEAD_LAG"
                    hold_time = 0
                    
            elif current_regime == "RANGE":
                # M9 Logic (Buy dip)
                if row['target'] <= row['lower_bb'] and row['rsi'] < 35:
                    in_position = True
                    entry_price = row['target']
                    strategy_mode = "RANGE_M9"
                    hold_time = 0

    # Analyze Results
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
        
    print("=== Regime-Switching Proof of Concept (Target: BNBUSDT) ===")
    print("Logic: ADX Daily Switcher (Lead-Lag for Trend / M9 for Range)\n")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R")
    print(f"Max Drawdown: {max_dd*100:.2f}%")

if __name__ == "__main__":
    main()
