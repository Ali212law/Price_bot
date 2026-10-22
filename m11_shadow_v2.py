import os, json, base64, requests, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "m11_shadow_v2_state.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return {}, None
    except: return {}, None

def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_klines(symbol, interval='1d', limit=50):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
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
    if not isinstance(state, dict) or "history" not in state:
        state = {"current_regime": "NEUTRAL", "history": []}
        
    btc_daily = fetch_klines("BTCUSDT", "1d", 50)
    if not btc_daily: return
    current_adx = calculate_daily_adx(btc_daily)
    prev_regime = state["current_regime"]
    
    if current_adx > 25: current_regime = "TREND"
    elif current_adx < 20: current_regime = "RANGE"
    else: current_regime = prev_regime
        
    # Triple Allocation Logic
    if current_regime == "TREND":
        w_ll, w_vsb, w_m9 = 0.5, 0.3, 0.2
    elif current_regime == "RANGE":
        w_m9, w_vsb, w_ll = 0.5, 0.3, 0.2
    else:
        w_m9, w_ll, w_vsb = 0.333, 0.333, 0.334
        
    log_entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "adx": current_adx,
        "regime": current_regime,
        "w_m9": w_m9,
        "w_lead_lag": w_ll,
        "w_vsb": w_vsb
    }
    
    state["history"].append(log_entry)
    if len(state["history"]) > 500: state["history"] = state["history"][-500:]
    state["current_regime"] = current_regime
    
    if save_to_github(STATE_FILE, state, sha):
        print(f"M11-V2 Shadow updated. Regime: {current_regime}")

if __name__ == "__main__":
    main()
