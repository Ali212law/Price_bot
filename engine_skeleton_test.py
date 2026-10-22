import requests
import pandas as pd
import numpy as np
import time

# --- 1. Strategy Interface (Plugins) ---
class Strategy:
    def __init__(self, name):
        self.name = name
        self.capital = 0.0
        self.position = None
        
    def generate_signal(self, row, df_context):
        """Returns 'BUY', 'SELL', or None"""
        raise NotImplementedError

class LeadLagStrategy(Strategy):
    def generate_signal(self, row, df_context):
        # Simple logic for demo: if BTC mom > 2% and Target mom < 0.5%
        if row['btc_mom'] > 0.02 and row['target_mom'] < 0.005:
            return 'BUY'
        # Time-based exit simulated by engine
        return None

class M9Strategy(Strategy):
    def generate_signal(self, row, df_context):
        # Simple logic: Price below lower BB and RSI < 35
        if row['target'] <= row['lower_bb'] and row['rsi'] < 35:
            return 'BUY'
        return None

# --- 2. The Capital Allocation Engine ---
class AllocationEngine:
    def __init__(self, initial_capital, strategies):
        self.total_capital = initial_capital
        self.strategies = {s.name: s for s in strategies}
        self.positions = {} # Track active trades
        self.equity_curve = [initial_capital]
        
    def get_weights(self, adx):
        # Regime Detection
        if adx > 25:
            return {"LeadLag": 0.7, "M9": 0.3} # Trend
        elif adx < 20:
            return {"LeadLag": 0.3, "M9": 0.7} # Range
        else:
            return {"LeadLag": 0.5, "M9": 0.5} # Neutral

    def execute_step(self, row, df_context, current_index):
        adx = row['adx']
        weights = self.get_weights(adx)
        
        # 1. Update existing positions (Check Exits)
        for strat_name, pos in list(self.positions.items()):
            # For demo: LeadLag exits after 3 periods, M9 exits if hit SMA or SL
            exit_trade = False
            
            if strat_name == "LeadLag":
                if current_index - pos['entry_index'] >= 3:
                    exit_trade = True
            elif strat_name == "M9":
                if row['target'] >= row['sma20'] or row['target'] <= pos['sl']:
                    exit_trade = True
                    
            if exit_trade:
                # Calculate PnL based on allocated capital at entry
                pnl_pct = (row['target'] - pos['entry_price']) / pos['entry_price']
                # Apply 0.2% fee
                net_pnl = (pos['allocated_capital'] * pnl_pct) - (pos['allocated_capital'] * 0.002)
                self.total_capital += net_pnl
                del self.positions[strat_name]
                
        # 2. Check for new signals
        for strat_name, strat in self.strategies.items():
            if strat_name not in self.positions:
                signal = strat.generate_signal(row, df_context)
                if signal == 'BUY':
                    # Allocate capital based on current total capital and weight
                    allocated_cap = self.total_capital * weights[strat_name]
                    
                    # In a real engine, we wouldn't allocate 100% of the weight to one trade, 
                    # but for this skeleton, we use it as position size.
                    sl_price = row['target'] - (2 * row['atr']) if strat_name == "M9" else 0
                    
                    self.positions[strat_name] = {
                        "entry_price": row['target'],
                        "entry_index": current_index,
                        "allocated_capital": allocated_cap,
                        "sl": sl_price
                    }

        # 3. Record Equity
        # Note: Equity = Cash + Unrealized PnL of open positions
        current_equity = self.total_capital
        for pos in self.positions.values():
            unrealized_pct = (row['target'] - pos['entry_price']) / pos['entry_price']
            current_equity += (pos['allocated_capital'] * unrealized_pct)
            
        self.equity_curve.append(current_equity)

# --- 3. Data Fetching & Setup ---
def fetch_klines(symbol, interval, days):
    # (Same fetching logic as before)
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
                    all_candles.append({"t": int(k[0]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])})
                end_time = data[0][0] - 1
            else: break
        except: break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    return pd.DataFrame(sorted(list(unique.values()), key=lambda x: x['t']))

def calculate_daily_adx(btc_daily):
    # (Same ADX logic as before)
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
    print("Fetching Data for Engine Simulation...")
    df_eth = fetch_klines('ETHUSDT', '4h', 730)
    df_btc = fetch_klines('BTCUSDT', '4h', 730)
    btc_daily = fetch_klines('BTCUSDT', '1d', 730)
    
    if df_eth.empty or df_btc.empty: return
    
    # Prep Indicators for ETH
    df_eth['sma20'] = df_eth['c'].rolling(20).mean()
    df_eth['std20'] = df_eth['c'].rolling(20).std()
    df_eth['lower_bb'] = df_eth['sma20'] - (2 * df_eth['std20'])
    delta = df_eth['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df_eth['rsi'] = 100 - (100 / (1 + (gain/loss)))
    df_eth['tr'] = np.maximum(df_eth['h'] - df_eth['l'], np.maximum(abs(df_eth['h'] - df_eth['c'].shift(1)), abs(df_eth['l'] - df_eth['c'].shift(1))))
    df_eth['atr'] = df_eth['tr'].rolling(14).mean()
    
    df_eth.rename(columns={'c': 'target', 't': 'time'}, inplace=True)
    df_btc.rename(columns={'c': 'btc', 't': 'time'}, inplace=True)
    
    df = pd.merge(df_eth[['time', 'target', 'sma20', 'lower_bb', 'rsi', 'atr']], df_btc[['time', 'btc']], on='time').dropna()
    
    # Merge ADX
    daily_adx = calculate_daily_adx(btc_daily)
    df['date'] = pd.to_datetime(df['time'], unit='ms').dt.date
    daily_adx['date'] = pd.to_datetime(daily_adx['t'], unit='ms').dt.date
    df = pd.merge(df, daily_adx[['date', 'adx']], on='date', how='left').ffill().dropna()
    
    # Momentum
    lookback = 14
    df['btc_mom'] = (df['btc'] / df['btc'].shift(lookback)) - 1
    df['target_mom'] = (df['target'] / df['target'].shift(lookback)) - 1
    df = df.dropna().reset_index(drop=True)
    
    # Initialize Engine
    strategies = [LeadLagStrategy("LeadLag"), M9Strategy("M9")]
    engine = AllocationEngine(initial_capital=1000.0, strategies=strategies)
    
    print("Running Engine Execution...")
    for i in range(1, len(df)):
        engine.execute_step(df.iloc[i], df.iloc[:i], i)
        
    # Results
    final_eq = engine.equity_curve[-1]
    peak = max(engine.equity_curve)
    max_dd = max([(peak - eq) / peak for eq in engine.equity_curve]) * 100
    net_pnl = ((final_eq - 1000) / 1000) * 100
    
    print("\n=== ENGINE EXECUTION RESULTS (V1 Skeleton) ===")
    print(f"Final Equity: ${final_eq:.2f}")
    print(f"Net PnL: {net_pnl:.2f}%")
    print(f"Max Drawdown: {max_dd:.2f}%")

if __name__ == "__main__":
    main()
