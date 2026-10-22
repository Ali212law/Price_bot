import os, json, base64, requests, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# --- RESILIENCE: Configure Session with Retries ---
def get_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = get_session()

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "vsb_signals.json"
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
            return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in r.json()]
    except: pass
    return []

def main():
    state, sha = load_from_github(STATE_FILE)
    if "signals" not in state: state["signals"] = []
    
    for symbol in SYMBOLS:
        df = pd.DataFrame(fetch_klines(symbol, '4h', 100))
        if df.empty: continue
        
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
        
        # Squeeze logic
        df['squeeze_on'] = (df['lower_bb'] > df['lower_kc']) & (df['upper_bb'] < df['upper_kc'])
        df['squeeze_count'] = df['squeeze_on'].groupby((df['squeeze_on'] != df['squeeze_on'].shift()).cumsum()).cumsum()
        
        df = df.dropna().reset_index(drop=True)
        
        # The last candle in df might be incomplete. We use the second to last as the last CLOSED candle.
        last_closed = df.iloc[-2]
        prev_closed = df.iloc[-3]
        current_time = last_closed['t']
        
        # 1. Check existing OPEN signals for this symbol (did they hit SL or TP on the last closed candle?)
        for sig in state["signals"]:
            if sig["symbol"] == symbol and sig["status"] == "open":
                # If the signal was opened on a previous candle
                if sig["entry_time"] < current_time:
                    if last_closed['l'] <= sig["sl"]:
                        sig.update({"status": "closed", "exit_time": current_time, "exit_price": sig["sl"], "exit_reason": "SL"})
                        print(f"[{symbol}] Signal {sig['id']} CLOSED at SL.")
                    elif last_closed['h'] >= sig["tp"]:
                        sig.update({"status": "closed", "exit_time": current_time, "exit_price": sig["tp"], "exit_reason": "TP"})
                        print(f"[{symbol}] Signal {sig['id']} CLOSED at TP.")
        
        # 2. Check for NEW signals
        # Ensure we don't double trigger on the same candle
        already_triggered = any(s["symbol"] == symbol and s["entry_time"] == current_time for s in state["signals"])
        
        if not already_triggered:
            # Condition: Prev candle had >= 4 squeeze count
            if prev_closed['squeeze_count'] >= 4:
                # Breakout: Close > Upper BB and Volume > 1.2 * Vol SMA
                if last_closed['c'] > last_closed['upper_bb'] and last_closed['v'] > (1.2 * last_closed['vol_sma']):
                    entry_price = last_closed['c']
                    sl_price = entry_price - (2 * last_closed['atr'])
                    tp_price = entry_price + (4 * last_closed['atr']) # TP is 2x the risk
                    
                    new_sig = {
                        "id": f"{current_time}_{symbol}",
                        "symbol": symbol,
                        "entry_time": current_time,
                        "entry_price": entry_price,
                        "sl": sl_price,
                        "tp": tp_price,
                        "status": "open",
                        "exit_time": None,
                        "exit_price": None,
                        "exit_reason": None
                    }
                    state["signals"].append(new_sig)
                    print(f"[{symbol}] NEW SIGNAL generated at {entry_price}")

    if save_to_github(STATE_FILE, state, sha):
        print("VSB Signals updated successfully.")

if __name__ == "__main__":
    main()
