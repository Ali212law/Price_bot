#!/usr/bin/env python3
# backtest_m7_historical.py — Historical Backtest for M7 (DCA + Premium Filter)
import requests, json, time
from datetime import datetime, timezone

# M7 Parameters
DCA_AMOUNT = 0.005 # 0.5% of capital per week
INITIAL_CAPITAL = 1000000000.0 # 1 Billion Toman for simulation
MAX_EXPOSURE = 0.30

def fetch_wallex_daily(symbol, days=1095): # 3 years
    now = int(time.time())
    start = now - (days * 24 * 3600)
    chunk = 14 * 24 * 3600
    candles = []
    current = start
    
    while current < now:
        to_ts = min(current + chunk, now)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={symbol}&resolution=1D&from={current}&to={to_ts}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get('s') == 'ok':
                for i in range(len(data['t'])):
                    c = float(data['c'][i])
                    if c > 100_000_000_000: c /= 10
                    candles.append({
                        "t": int(data['t'][i]),
                        "c": c
                    })
        except Exception as e:
            print(f"Fetch error: {e}")
        current = to_ts
        time.sleep(0.3)
    
    candles.sort(key=lambda x: x['t'])
    # remove duplicates
    unique = {c['t']: c for c in candles}
    return list(unique.values())

def main():
    print("Fetching BTC/TMN daily data (3 years)...")
    btc_tmn = fetch_wallex_daily("BTCTMN", 1095)
    
    print("Fetching USDT/TMN daily data (3 years)...")
    usdt_tmn = fetch_wallex_daily("USDTTMN", 1095)
    
    # Align by day
    usdt_dict = {c['t'] // 86400: c['c'] for c in usdt_tmn}
    
    aligned_data = []
    for b in btc_tmn:
        day = b['t'] // 86400
        if day in usdt_dict:
            aligned_data.append({
                "t": b['t'],
                "btc_tmn": b['c'],
                "usdt_tmn": usdt_dict[day]
            })
            
    print(f"Aligned {len(aligned_data)} days of data.")
    if len(aligned_data) < 100:
        print("Not enough data.")
        return

    # Simulate DCA (Every Monday)
    dca_capital = INITIAL_CAPITAL
    dca_btc = 0.0
    dca_trades = []
    
    # Simulate Premium Filter DCA
    filtered_capital = INITIAL_CAPITAL
    filtered_btc = 0.0
    filtered_trades = []
    
    # Simple moving average of premium for filter
    premium_history = []
    
    for i in range(20, len(aligned_data)):
        row = aligned_data[i]
        dt = datetime.fromtimestamp(row['t'], tz=timezone.utc)
        
        # Calculate premium proxy (BTC_TMN / USDT_TMN vs BTC_USD - approximated as price action)
        # Since we don't have BTC_USD here, we just use the premium of USDT relative to its 20-day average
        # Actually, the M7 premium is about USDT/TMN vs USD_Free. We don't have USD_Free.
        # We will use the 30-day moving average of USDT_TMN as a proxy for "normal" premium.
        
        premium_history.append(row['usdt_tmn'])
        if len(premium_history) > 30:
            premium_history.pop(0)
            
        avg_usdt = sum(premium_history) / len(premium_history)
        premium_pct = ((row['usdt_tmn'] - avg_usdt) / avg_usdt) * 100
        
        # Only buy on Mondays
        if dt.weekday() == 0:
            # 1. Blind DCA
            buy_amount = dca_capital * DCA_AMOUNT
            if dca_btc * row['btc_tmn'] < (dca_capital * MAX_EXPOSURE):
                dca_btc += buy_amount / row['btc_tmn']
                dca_trades.append({"date": dt.strftime("%Y-%m-%d"), "price": row['btc_tmn'], "amount": buy_amount})
                
            # 2. Filtered DCA (Buy double if premium < -1%, half if premium > 2%)
            f_buy_amount = filtered_capital * DCA_AMOUNT
            if premium_pct > 2.0:
                f_buy_amount *= 0.5
            elif premium_pct < -1.0:
                f_buy_amount *= 2.0
                
            if filtered_btc * row['btc_tmn'] < (filtered_capital * MAX_EXPOSURE):
                filtered_btc += f_buy_amount / row['btc_tmn']
                filtered_trades.append({"date": dt.strftime("%Y-%m-%d"), "price": row['btc_tmn'], "amount": f_buy_amount, "premium": round(premium_pct, 2)})

    final_btc_tmn = aligned_data[-1]['btc_tmn']
    
    blind_value = dca_btc * final_btc_tmn + (dca_capital - sum(t['amount'] for t in dca_trades))
    filtered_value = filtered_btc * final_btc_tmn + (filtered_capital - sum(t['amount'] for t in filtered_trades))
    bh_value = INITIAL_CAPITAL * (final_btc_tmn / aligned_data[20]['btc_tmn'])
    
    print("\n=== M7 Historical Backtest (3 Years) ===")
    print(f"Start Price (BTC/TMN): {aligned_data[20]['btc_tmn']:,.0f}")
    print(f"End Price (BTC/TMN): {final_btc_tmn:,.0f}")
    print(f"\n1. Buy & Hold Value: {bh_value:,.0f} Toman ({(bh_value/INITIAL_CAPITAL-1)*100:.1f}%)")
    print(f"2. Blind DCA Value: {blind_value:,.0f} Toman ({(blind_value/INITIAL_CAPITAL-1)*100:.1f}%) | Trades: {len(dca_trades)}")
    print(f"3. Filtered DCA Value: {filtered_value:,.0f} Toman ({(filtered_value/INITIAL_CAPITAL-1)*100:.1f}%) | Trades: {len(filtered_trades)}")

if __name__ == "__main__":
    main()
