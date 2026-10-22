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

def backtest_vsb(df, symbol):
    # Indicators
    df['sma20'] = df['c'].rolling(window=20).mean()
    df['std20'] = df['c'].rolling(window=20).std()
    df['upper_bb'] = df['sma20'] + (2 * df['std20'])
    df['lower_bb'] = df['sma20'] - (2 * df['std20'])
    
    df['ema20'] = df['c'].ewm(span=20, adjust=False).mean()
    df['tr'] = np.maximum(df['h'] - df['l'], np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    df['upper_kc'] = df['ema20'] + (1.5 * df['atr'])
    df['lower_kc'] = df['ema20'] - (1.5 * df['atr'])
    
    df['vol_sma'] = df['v'].rolling(window=20).mean()
    
    # Squeeze Condition: BB inside KC
    df['squeeze_on'] = (df['lower_bb'] > df['lower_kc']) & (df['upper_bb'] < df['upper_kc'])
    
    # Count consecutive squeeze periods
    df['squeeze_count'] = df['squeeze_on'].groupby((df['squeeze_on'] != df['squeeze_on'].shift()).cumsum()).cumsum()
    
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    in_position = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    pos_size = 0
    
    trades = []
    equity_curve = [equity]
    fee_rate = 0.001
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        
        if in_position:
            if row['l'] <= sl_price:
                # Hit Stop Loss
                gross_return = (sl_price - entry_price) / entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (pos_size * (sl_price - entry_price)) - (pos_size * entry_price * 2 * fee_rate)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
            elif row['h'] >= tp_price:
                # Hit Take Profit
                gross_return = (tp_price - entry_price) / entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (pos_size * (tp_price - entry_price)) - (pos_size * entry_price * 2 * fee_rate)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
        else:
            # Entry Condition: Squeeze was on for >= 4 periods, then break out with volume
            if df['squeeze_count'].iloc[i-1] >= 4:
                if row['c'] > row['upper_bb'] and row['v'] > (1.2 * row['vol_sma']):
                    # Long Breakout
                    in_position = True
                    entry_price = row['c']
                    sl_price = entry_price - (2 * row['atr'])
                    tp_price = entry_price + (2 * (entry_price - sl_price)) # 2x SL (M9 Style)
                    
                    risk_per_unit = entry_price - sl_price
                    if risk_per_unit <= 0: 
                        in_position = False
                        continue
                        
                    risk_amount = equity * 0.005 # 0.5% Risk
                    pos_size = risk_amount / risk_per_unit
                    if (pos_size * entry_price) > equity:
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
    
    net_pnl = ((equity - 1000.0) / 1000.0) * 100
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
    
    print(f"--- {symbol} (TTM Squeeze Standalone) ---")
    print(f"Total Trades: {total_trades} | Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"Net PnL: {net_pnl:.2f}% | PF: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R | MaxDD: {max_dd*100:.2f}%")
    print(f"Wilson: {wilson_lower:.2f}% | Top 5 Concentration: {top_5_concentration:.1f}%\n")

if __name__ == "__main__":
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    print("=== Backtest of Volatility Squeeze (TTM Standard) ===")
    print("Parameters: BB inside KC, 4+ Squeeze Candles, Vol > 1.2x, SL=2ATR, TP=2SL\n")
    for sym in symbols:
        df = fetch_klines(sym, '4h', 730)
        if not df.empty:
            backtest_vsb(df, sym)
