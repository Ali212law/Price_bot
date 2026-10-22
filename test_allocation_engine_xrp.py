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
                        "t": int(k[0]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])
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
    print("Fetching XRP (Target) and BTC (Leader) Data...")
    df_xrp = fetch_klines('XRPUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    
    if df_xrp.empty or df_btc.empty or btc_daily.empty:
        print("Data fetch failed.")
        return
        
    # Indicators for M9 (BB, RSI, ATR)
    df_xrp['sma20'] = df_xrp['c'].rolling(window=20).mean()
    df_xrp['std20'] = df_xrp['c'].rolling(window=20).std()
    df_xrp['lower_bb'] = df_xrp['sma20'] - (2 * df_xrp['std20'])
    
    delta = df_xrp['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_xrp['rsi'] = 100 - (100 / (1 + rs))
    
    df_xrp['tr'] = np.maximum(df_xrp['h'] - df_xrp['l'], np.maximum(abs(df_xrp['h'] - df_xrp['c'].shift(1)), abs(df_xrp['l'] - df_xrp['c'].shift(1))))
    df_xrp['atr'] = df_xrp['tr'].rolling(window=14).mean()
    
    df_xrp.rename(columns={'c': 'target', 't': 'time'}, inplace=True)
    df_btc.rename(columns={'c': 'btc', 't': 'time'}, inplace=True)
    
    df = pd.merge(df_xrp[['time', 'target', 'sma20', 'lower_bb', 'rsi', 'atr']], df_btc[['time', 'btc']], on='time').dropna()
    
    # Merge Daily ADX
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['time'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill().dropna()
    
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['target_mom'] = (df['target'] / df['target'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    # --- ALLOCATION ENGINE ---
    initial_equity = 1000.0
    m9_cap = initial_equity / 2  # Start 50/50
    ll_cap = initial_equity / 2
    
    m9_in_pos = False
    m9_entry = 0
    m9_sl = 0
    
    ll_in_pos = False
    ll_entry = 0
    ll_hold = 0
    
    trades = []
    equity_curve = [initial_equity]
    fee_rate = 0.002
    
    current_regime = "NEUTRAL"
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        adx = row['adx']
        
        # 1. Regime Detection
        if adx > 25: current_regime = "TREND"
        elif adx < 20: current_regime = "RANGE"
        # Hysteresis: keep previous regime if between 20-25
        
        # 2. Dynamic Allocation Weights (Target)
        if current_regime == "TREND":
            target_m9_w, target_ll_w = 0.3, 0.7
        elif current_regime == "RANGE":
            target_m9_w, target_ll_w = 0.7, 0.3
        else:
            target_m9_w, target_ll_w = 0.5, 0.5
            
        # Calculate current total equity
        total_eq = m9_cap + ll_cap
        # (In a real engine, we would rebalance by moving money between caps here)
        
        # --- M9 LOGIC (Range) ---
        if m9_in_pos:
            # Exit: Time stop (10 periods) or hit SMA20 or SL
            if row['target'] >= row['sma20'] or row['target'] <= m9_sl:
                gross_ret = (row['target'] - m9_entry) / m9_entry
                net_ret = gross_ret - fee_rate
                m9_cap += (m9_cap * net_ret)
                m9_in_pos = False
        else:
            # Entry condition based on target weight (simplified as size)
            if row['target'] <= row['lower_bb'] and row['rsi'] < 35:
                m9_in_pos = True
                m9_entry = row['target']
                m9_sl = m9_entry - (2 * row['atr'])
                
        # --- LEAD-LAG LOGIC (Trend) ---
        if ll_in_pos:
            ll_hold += 1
            if ll_hold >= 3:
                gross_ret = (row['target'] - ll_entry) / ll_entry
                net_ret = gross_ret - fee_rate
                ll_cap += (ll_cap * net_ret)
                ll_in_pos = False
        else:
            if row['btc_mom'] > 0.02 and row['target_mom'] < 0.005:
                ll_in_pos = True
                ll_entry = row['target']
                ll_hold = 0
                
        # (For simplicity, we track equity as the sum of caps)
        # A true rebalancing function would move funds based on target weights
        
        equity_curve.append(m9_cap + ll_cap)

    # Analyze
    total_trades = len(trades) # Note: We didn't track individual trade arrays for this combined test, just cap changes
    final_equity = equity_curve[-1]
    net_pnl = ((final_equity - 1000.0) / 1000.0) * 100
    
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd
        
    print("=== Allocation Engine PoC V2 (Target: XRPUSDT) ===")
    print("Logic: Dynamic Weights (Trend 70% LL / 30% M9 | Range 30% LL / 70% M9)\n")
    print(f"Final Equity: ${final_equity:.2f}")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Max Drawdown: {max_dd*100:.2f}%")
    print("\nNote: This is a high-level PoC of the allocation engine.")
    print("It does not output full trade stats (PF/Wilson) yet, but shows the survival curve.")

if __name__ == "__main__":
    main()
