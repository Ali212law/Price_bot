#!/usr/bin/env python3
# paper_trade_m10.py — M10 HODL Bot (Buy in 3 parts, then hold forever)

import os, json, base64, requests
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "paper_m10_trades.json"
INITIAL_CAPITAL = 1000000000.0 # 1 Billion Toman
TOTAL_FEE = 0.6 # 0.6% fee

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
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_btc_price():
    url = "https://api.wallex.ir/v1/markets"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        btc = data.get("result", {}).get("symbols", {}).get("BTCTMN", {})
        return float(btc.get("stats", {}).get("lastPrice", 0))
    except: return 0.0

def main():
    now = datetime.now(timezone.utc)
    state, sha = load_from_github(STATE_FILE)
    
    # Initialize
    if not isinstance(state, dict) or "step" not in state:
        state = {
            "capital": INITIAL_CAPITAL,
            "btc_amount": 0.0,
            "step": 0,
            "status": "buying",
            "start_price": 0.0,
            "trades": []
        }

    price = fetch_btc_price()
    if price == 0:
        print("Failed to fetch BTC price.")
        return

    if state["status"] == "buying":
        if state["start_price"] == 0.0:
            state["start_price"] = price
            
        step = state["step"]
        if step < 3:
            # Calculate buy amount (33%, 33%, 34%)
            if step == 0: pct = 0.33
            elif step == 1: pct = 0.33
            else: pct = 0.34
            
            buy_toman = INITIAL_CAPITAL * pct
            fee_toman = buy_toman * (TOTAL_FEE / 100)
            net_buy = buy_toman - fee_toman
            
            btc_bought = net_buy / price
            state["btc_amount"] += btc_bought
            state["capital"] -= buy_toman
            state["step"] += 1
            
            trade_record = {
                "time": now.isoformat(),
                "step": state["step"],
                "price": price,
                "buy_toman": buy_toman,
                "btc_bought": btc_bought
            }
            state["trades"].append(trade_record)
            
            print(f"[M10] BUY STEP {state['step']}/3 | Price: {price:,.0f} | BTC: {btc_bought:.8f}")
            
            if state["step"] == 3:
                state["status"] = "holding"
                print("[M10] ALL BUYS COMPLETED. STATUS: HOLDING FOREVER.")

    elif state["status"] == "holding":
        current_value = state["btc_amount"] * price
        total_value = current_value + state["capital"]
        roi = ((total_value / INITIAL_CAPITAL) - 1) * 100
        
        print(f"[M10] HOLDING | Current Price: {price:,.0f}")
        print(f"[M10] Portfolio Value: {total_value:,.0f} Toman | ROI: {roi:+.2f}%")

    state["last_run"] = now.isoformat()
    if save_to_github(STATE_FILE, state, sha):
        print("M10 state saved.")

if __name__ == "__main__":
    main()
