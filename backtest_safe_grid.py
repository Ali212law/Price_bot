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

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def backtest_grid(df, btc_daily, symbol):
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['t'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill()
    df = df.dropna().reset_index(drop=True)
    
    equity = 1000.0
    trades = []
    equity_curve = [equity]
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
            
            # Check Hard SL (10% drop from initial entry)
            if current_price <= initial_entry_price * 0.90:
                # Close all at current price (gap down)
                gross_return = (current_price - avg_entry_price) / avg_entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (total_invested * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                continue
                
            # Check TP (2% above average)
            if current_price >= avg_entry_price * 1.02:
                gross_return = (current_price - avg_entry_price) / avg_entry_price
                net_return = gross_return - (2 * fee_rate)
                equity += (total_invested * net_return)
                trades.append(net_return)
                equity_curve.append(equity)
                in_position = False
                continue
                
            # Check for additional levels
            if levels == 1 and current_price <= initial_entry_price * 0.97:
                # Buy level 2
                amount = (equity * 0.005) / 0.03 # 0.5% risk, assuming 3% drop
                amount = min(amount, equity / 3) # Max 1/3 of equity per level
                total_units += amount / current_price
                total_invested += amount
                levels = 2
            elif levels == 2 and current_price <= initial_entry_price * 0.94:
                # Buy level 3
                amount = (equity * 0.005) / 0.06
                amount = min(amount, equity / 3)
                total_units += amount / current_price
                total_invested += amount
                levels = 3
        else:
            # Entry condition: ADX < 20
            if adx < 20:
                in_position = True
                levels = 1
                initial_entry_price = current_price
                amount = equity / 3 # Use 1/3 of total equity for the first level
                total_units = amount / current_price
                total_invested = amount
                
        equity_curve.append(equity) # Note: Unrealized PnL is not reflected here, just for simplicity

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
    
    print(f"--- {symbol} (Safe Grid) ---")
    print(f"Total Trades: {total_trades} | Wins: {win_count} | Losses: {total_trades - win_count}")
    print(f"Net PnL: {net_pnl:.2f}% | PF: {pf:.2f}")
    print(f"Expectancy: {expectancy:.3f}R | MaxDD: {max_dd*100:.2f}%")
    print(f"Wilson: {wilson_lower:.2f}% | Top 5 Concentration: {top_5_concentration:.1f}%\n")

if __name__ == "__main__":
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    print("=== Backtest of Safe Grid (Range Only) ===")
    print("Logic: ADX<20, 3 Levels (0%, -3%, -6%), TP=+2%, Hard SL=-10%\n")
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    for sym in symbols:
        df = fetch_klines(sym, '4h', 730)
        if not df.empty and not btc_daily.empty:
            backtest_grid(df, btc_daily, sym)
