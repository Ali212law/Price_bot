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
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                        "l": float(k[3]), "c": float(k[4]), "v": float(k[5])
                    })
                end_time = data[0][0] - 1
            else: break
        except Exception as e: 
            print(f"Error fetching data: {e}")
            break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    sorted_candles = sorted(list(unique.values()), key=lambda x: x['t'])
    df = pd.DataFrame(sorted_candles)
    return df

def calculate_supertrend(df, period=10, multiplier=3.0):
    high = df['h'].values
    low = df['l'].values
    close = df['c'].values
    
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    
    atr = np.zeros_like(close)
    atr[period-1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    trend = np.ones(len(close), dtype=int)
    
    for i in range(1, len(close)):
        if close[i] > upperband[i-1]:
            trend[i] = 1
        elif close[i] < lowerband[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
            if trend[i] == 1 and lowerband[i] < lowerband[i-1]:
                lowerband[i] = lowerband[i-1]
            if trend[i] == -1 and upperband[i] > upperband[i-1]:
                upperband[i] = upperband[i-1]
                
    df['trend'] = trend
    df['upper'] = upperband
    df['lower'] = lowerband
    df['close'] = close
    return df

def audit_backtest(df, symbol):
    initial_equity = 1000.0
    equity = initial_equity
    risk_per_trade = 0.005 # 0.5% Risk
    fee_rate = 0.001 # 0.1% per side (0.2% RT)
    
    in_position = False
    entry_price = 0
    sl_price = 0
    pos_size = 0
    entry_idx = 0
    
    equity_curve = [equity]
    trades = []
    
    trend = df['trend'].values
    close = df['close'].values
    lower = df['lower'].values
    upper = df['upper'].values
    
    for i in range(1, len(df)):
        # Entry
        if trend[i] == 1 and trend[i-1] == -1 and not in_position:
            in_position = True
            entry_price = close[i]
            sl_price = lower[i] # SuperTrend stop loss is the lower band
            risk_per_unit = entry_price - sl_price
            
            if risk_per_unit <= 0:
                in_position = False
                continue
                
            risk_amount = equity * risk_per_trade
            pos_size = risk_amount / risk_per_unit
            
            # Check for leverage (cap at 1x for spot)
            cost = pos_size * entry_price
            if cost > equity:
                pos_size = equity / entry_price
                
            entry_idx = i
            
        # Exit
        elif trend[i] == -1 and trend[i-1] == 1 and in_position:
            in_position = False
            exit_price = close[i]
            
            # Calculate PnL
            gross_pnl = (exit_price - entry_price) * pos_size
            fees = (entry_price * pos_size * fee_rate) + (exit_price * pos_size * fee_rate)
            net_pnl = gross_pnl - fees
            
            equity += net_pnl
            equity_curve.append(equity)
            
            trades.append({
                "entry_time": df['t'].iloc[entry_idx],
                "exit_time": df['t'].iloc[i],
                "entry": entry_price,
                "exit": exit_price,
                "sl": sl_price,
                "size": pos_size,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "equity": equity
            })
            
    # Calculate MaxDD
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
        
    print(f"--- AUDIT REPORT: {symbol} ---")
    print(f"Initial Equity: ${initial_equity:.2f} | Final Equity: ${equity:.2f}")
    print(f"Total Trades: {len(trades)}")
    print(f"Risk per trade: {risk_per_trade*100}% of Equity")
    print(f"Max Drawdown (Compounded): {max_dd*100:.2f}%")
    
    print("\nFirst 5 Trades Detail:")
    for t in trades[:5]:
        print(f"  Entry: {t['entry']:.2f} | SL: {t['sl']:.2f} | Size: {t['size']:.4f} | Net PnL: ${t['net_pnl']:.2f}")
    print("\n")

if __name__ == "__main__":
    symbols = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
    print("=== Starting SuperTrend Risk Management Audit ===\n")
    for symbol in symbols:
        df = fetch_klines(symbol, '4h', 730)
        if df.empty: continue
        df = calculate_supertrend(df)
        audit_backtest(df, symbol)
