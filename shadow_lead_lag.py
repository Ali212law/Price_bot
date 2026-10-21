import os, json, base64, requests, time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")
STATE_FILE = "shadow_lead_lag_trades.json"
INITIAL_CAPITAL = 1000.0
HEADERS = {"User-Agent": "Mozilla/5.0"}

def send_bale(msg):
    if not BALE_TOKEN or not BALE_CHAT: return
    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": BALE_CHAT, "text": msg}, timeout=10)
    except: pass

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
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_klines(symbol):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=4h&limit=100"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return [{"t": int(k[0]), "c": float(k[4])} for k in r.json()]
    except: pass
    return []

def main():
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "trades" not in state:
        state = {"capital": INITIAL_CAPITAL, "trades": []}
    
    btc_data = fetch_klines("BTCUSDT")
    eth_data = fetch_klines("ETHUSDT")
    if not btc_data or not eth_data: 
        print("Data fetch failed.")
        return
    
    btc_close = [c['c'] for c in btc_data]
    eth_close = [c['c'] for c in eth_data]
    current_time = btc_data[-1]['t']
    
    open_positions = [t for t in state["trades"] if t["status"] == "open"]
    for t in open_positions[:]:
        if current_time - t["entry_time"] >= (3 * 4 * 3600 * 1000):
            exit_price = eth_close[-1]
            gross_return = (exit_price - t["entry_price"]) / t["entry_price"]
            net_return = gross_return - 0.002 # 0.2% RT fee
            pnl = t["amount"] * net_return
            state["capital"] += pnl
            t.update({"status": "closed", "exit_time": current_time, "exit_price": exit_price, "pnl": pnl})
            
            emoji = "🟢" if pnl > 0 else "🔴"
            send_bale(f"{emoji} SHADOW Lead-Lag CLOSED | ETH at {exit_price:.2f} | PnL: {pnl:.2f} USDT")
            print(f"Closed ETH position at {exit_price} | PnL: {pnl:.2f} USDT")
            open_positions.remove(t)
            
    if len(open_positions) == 0:
        lookback = 14
        if len(btc_close) > lookback:
            btc_mom = (btc_close[-1] / btc_close[-lookback]) - 1
            eth_mom = (eth_close[-1] / eth_close[-lookback]) - 1
            
            if btc_mom > 0.02 and eth_mom < 0.005:
                amount = state["capital"] * 0.1
                t = {
                    "entry_time": current_time,
                    "entry_price": eth_close[-1],
                    "amount": amount,
                    "status": "open"
                }
                state["trades"].append(t)
                send_bale(f"🟢 SHADOW Lead-Lag OPENED | LONG ETH at {eth_close[-1]:.2f}")
                print(f"Opened LONG on ETH at {eth_close[-1]}")
                
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    if save_to_github(STATE_FILE, state, sha):
        print(f"State updated. Capital: {state['capital']:.2f} USDT")

if __name__ == "__main__":
    main()
