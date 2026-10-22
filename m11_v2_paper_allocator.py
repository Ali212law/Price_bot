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
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")

STATE_FILE = "m11_v2_portfolio.json"
M9_FILE = "paper_m9_trades.json"
LL_FILE = "shadow_lead_lag_trades.json"
VSB_FILE = "vsb_signals.json"

INITIAL_CAPITAL = 10000.0
HEADERS = {"User-Agent": "Mozilla/5.0"}

def send_bale(msg):
    if not BALE_TOKEN or not BALE_CHAT: return
    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    try: session.post(url, json={"chat_id": BALE_CHAT, "text": msg}, timeout=10)
    except: pass

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = session.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
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
        r = session.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_klines(symbol, interval='4h', limit=10):
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

def get_current_price(symbol):
    data = fetch_klines(symbol, '4h', 2)
    if data: return data[-1]['c']
    return 0.0

def main():
    # 1. Load State
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "capital" not in state:
        state = {"capital": INITIAL_CAPITAL, "open_positions": [], "history": []}
        
    m9_data, _ = load_from_github(M9_FILE)
    ll_data, _ = load_from_github(LL_FILE)
    vsb_data, _ = load_from_github(VSB_FILE)
    
    btc_daily = fetch_klines("BTCUSDT", "1d", 50)
    if not btc_daily: return
    adx = calculate_daily_adx(btc_daily)
    
    # 2. Determine Regime and Weights
    if adx > 25:
        regime = "TREND"
        w_m9, w_vsb, w_ll = 0.2, 0.3, 0.5
    elif adx < 20:
        regime = "RANGE"
        w_m9, w_vsb, w_ll = 0.5, 0.3, 0.2
    else:
        regime = "NEUTRAL"
        w_m9, w_vsb, w_ll = 0.333, 0.333, 0.334

    # 3. Manage Open Positions (Check for Exits)
    for pos in state["open_positions"][:]:
        current_price = get_current_price(pos["symbol"])
        if current_price == 0: continue
        
        exit_triggered = False
        exit_price = current_price
        
        if pos["strategy"] == "M9":
            if current_price <= pos["sl"]: exit_triggered, exit_price = True, pos["sl"]
            elif current_price >= pos["tp"]: exit_triggered, exit_price = True, pos["tp"]
        elif pos["strategy"] == "VSB":
            if current_price <= pos["sl"]: exit_triggered, exit_price = True, pos["sl"]
            elif current_price >= pos["tp"]: exit_triggered, exit_price = True, pos["tp"]
        elif pos["strategy"] == "LL":
            # Time-based exit (12 hours = 3 periods of 4H)
            if time.time() * 1000 - pos["entry_time"] >= (3 * 4 * 3600 * 1000):
                exit_triggered, exit_price = True, current_price
                
        if exit_triggered:
            pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            net_pnl = (pos["allocated_capital"] * pnl_pct) - (pos["allocated_capital"] * 0.002)
            state["capital"] += net_pnl
            
            emoji = "🟢" if net_pnl > 0 else "🔴"
            send_bale(f"{emoji} M11-V2 CLOSED | {pos['strategy']} on {pos['symbol']} | PnL: {net_pnl:.2f} USDT")
            state["open_positions"].remove(pos)
            
    # 4. Sync New Signals
    # Helper to avoid duplicates
    def is_already_open(strategy, entry_time, symbol):
        return any(p["strategy"] == strategy and p["entry_time"] == entry_time and p["symbol"] == symbol for p in state["open_positions"])
        
    # Sync M9
    if isinstance(m9_data, dict):
        for t in m9_data.get("trades", []):
            if t.get("status") == "open" and not is_already_open("M9", t["entry_time"], t["symbol"]):
                risk_amount = state["capital"] * w_m9 * 0.005
                risk_per_unit = t["entry_price"] - t["sl"]
                if risk_per_unit > 0:
                    size = risk_amount / risk_per_unit
                    state["open_positions"].append({
                        "strategy": "M9", "symbol": t["symbol"], "entry_time": t["entry_time"],
                        "entry_price": t["entry_price"], "sl": t["sl"], "tp": t["tp"],
                        "allocated_capital": size * t["entry_price"]
                    })
                    
    # Sync LL (No SL, just time exit)
    if isinstance(ll_data, dict):
        for t in ll_data.get("trades", []):
            if t.get("status") == "open" and not is_already_open("LL", t["entry_time"], t["symbol"]):
                allocated_capital = state["capital"] * w_ll * 0.1 # 10% of weighted capital
                state["open_positions"].append({
                    "strategy": "LL", "symbol": t["symbol"], "entry_time": t["entry_time"],
                    "entry_price": t["entry_price"], "sl": 0, "tp": 0,
                    "allocated_capital": allocated_capital
                })
                
    # Sync VSB
    if isinstance(vsb_data, dict):
        for s in vsb_data.get("signals", []):
            if s.get("status") == "open" and not is_already_open("VSB", s["entry_time"], s["symbol"]):
                risk_amount = state["capital"] * w_vsb * 0.005
                risk_per_unit = s["entry_price"] - s["sl"]
                if risk_per_unit > 0:
                    size = risk_amount / risk_per_unit
                    state["open_positions"].append({
                        "strategy": "VSB", "symbol": s["symbol"], "entry_time": s["entry_time"],
                        "entry_price": s["entry_price"], "sl": s["sl"], "tp": s["tp"],
                        "allocated_capital": size * s["entry_price"]
                    })

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["regime"] = regime
    state["adx"] = adx
    
    if save_to_github(STATE_FILE, state, sha):
        print(f"M11-V2 Paper Allocator updated. Regime: {regime}, Open Positions: {len(state['open_positions'])}")

if __name__ == "__main__":
    main()
