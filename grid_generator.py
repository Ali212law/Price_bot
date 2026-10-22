import os, json, base64, requests, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def get_session():
    session = requests.Session()
    retry = Retry(total=5, read=5, connect=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = get_session()

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "grid_signals.json"
SYMBOLS = ['ETHUSDT', 'SOLUSDT', 'SUIUSDT']
HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = session.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return {"signals": []}, None
    except: return {"signals": []}, None

def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = session.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_klines(symbol, interval='4h', limit=100):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return [{"t": int(k[0]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])} for k in r.json()]
    except: pass
    return []

def calculate_daily_adx(btc_daily):
    if len(btc_daily) < 30: return 0.0
    df = pd.DataFrame(btc_daily)
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
    return round(df['adx'].iloc[-1], 2)

def main():
    state, sha = load_from_github(STATE_FILE)
    if "signals" not in state: state["signals"] = []
    
    btc_daily = fetch_klines("BTCUSDT", "1d", 50)
    if not btc_daily: return
    current_adx = calculate_daily_adx(btc_daily)
    
    # === FIX: Regime change -> close all open positions ===
    if current_adx >= 20:
        print(f"ADX is {current_adx} (>=20). Grid inactive - closing open positions.")
        any_closed = False
        for symbol in SYMBOLS:
            candles = fetch_klines(symbol, '4h', 10)
            if not candles or len(candles) < 2: continue
            last_closed = candles[-2]  # FIX: Use last closed candle
            for sig in state["signals"]:
                if sig["symbol"] == symbol and sig["status"] == "open":
                    sig.update({
                        "status": "closed",
                        "exit_time": last_closed['t'],
                        "exit_price": last_closed['c'],
                        "exit_reason": "REGIME_CHANGE"
                    })
                    any_closed = True
                    print(f"[{symbol}] Closed at REGIME_CHANGE: {last_closed['c']}")
        if any_closed:
            save_to_github(STATE_FILE, state, sha)
        return

    # === Normal Range logic ===
    for symbol in SYMBOLS:
        candles = fetch_klines(symbol, '4h', 100)
        if not candles or len(candles) < 2: continue
        
        # FIX: Use last CLOSED candle (index -2), not the current unfinished one
        last_closed = candles[-2]
        current_price = last_closed['c']
        current_time = last_closed['t']
        
        active_signals = [s for s in state["signals"] if s["symbol"] == symbol and s["status"] == "open"]
        
        for sig in active_signals:
            if current_price >= sig["avg_entry"] * 1.02:
                sig.update({"status": "closed", "exit_time": current_time, "exit_price": current_price, "exit_reason": "TP"})
                print(f"[{symbol}] Grid Closed at TP: {current_price}")
            elif current_price <= sig["initial_entry"] * 0.90:
                sig.update({"status": "closed", "exit_time": current_time, "exit_price": current_price, "exit_reason": "SL"})
                print(f"[{symbol}] Grid Closed at Hard SL: {current_price}")
            else:
                if sig["levels"] == 1 and current_price <= sig["initial_entry"] * 0.97:
                    sig["levels"] = 2
                    sig["total_invested"] += sig["amount_per_level"]
                    sig["total_units"] += sig["amount_per_level"] / current_price
                    sig["avg_entry"] = sig["total_invested"] / sig["total_units"]
                    print(f"[{symbol}] Added Level 2 at {current_price}")
                elif sig["levels"] == 2 and current_price <= sig["initial_entry"] * 0.94:
                    sig["levels"] = 3
                    sig["total_invested"] += sig["amount_per_level"]
                    sig["total_units"] += sig["amount_per_level"] / current_price
                    sig["avg_entry"] = sig["total_invested"] / sig["total_units"]
                    print(f"[{symbol}] Added Level 3 at {current_price}")
        
        if not [s for s in state["signals"] if s["symbol"] == symbol and s["status"] == "open"]:
            virtual_cap = 1000.0
            amount_per_level = virtual_cap / 3
            
            new_sig = {
                "id": f"{current_time}_{symbol}",
                "symbol": symbol,
                "entry_time": current_time,
                "initial_entry": current_price,
                "levels": 1,
                "amount_per_level": amount_per_level,
                "total_invested": amount_per_level,
                "total_units": amount_per_level / current_price,
                "avg_entry": current_price,
                "status": "open",
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None
            }
            state["signals"].append(new_sig)
            print(f"[{symbol}] Opened Level 1 at {current_price}")

    if save_to_github(STATE_FILE, state, sha):
        print("Grid Signals updated successfully.")

if __name__ == "__main__":
    main()
