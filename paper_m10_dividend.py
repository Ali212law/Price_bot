#!/usr/bin/env python3
# paper_m10_dividend.py — M10-Dividend: Buy 3 days, sell 0.5% monthly to USDT
import os, json, base64, requests
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")
STATE_FILE = "paper_m10_dividend.json"
INITIAL_CAPITAL = 1000000000.0
TOTAL_FEE = 0.6
MONTHLY_SELL_PCT = 0.005
MAX_CUMULATIVE_SELL = 0.50

def send_bale(msg):
    if not BALE_TOKEN or not BALE_CHAT:
        print("BALE: Tokens missing")
        return
    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": BALE_CHAT, "text": msg}, timeout=10)
        if r.status_code != 200:
            print(f"BALE Error: {r.text}")
    except Exception as e:
        print(f"BALE Exception: {e}")

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

def fetch_prices():
    """Returns (btc_tmn_price, usdt_tmn_price) or (None, None)"""
    url = "https://api.wallex.ir/v1/markets"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        usdt = float(symbols.get("USDTTMN", {}).get("stats", {}).get("lastPrice", 0))
        return btc, usdt
    except: return 0.0, 0.0

def main():
    now = datetime.now(timezone.utc)
    current_month = now.year * 12 + now.month
    
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "step" not in state:
        state = {
            "capital": INITIAL_CAPITAL,
            "btc_amount": 0.0,
            "usdt_amount": 0.0,
            "original_btc": 0.0,
            "cumulative_sold": 0.0,
            "step": 0,
            "status": "buying",
            "start_price": 0.0,
            "last_sale_month": 0,
            "trades": []
        }

    btc_price, usdt_price = fetch_prices()
    if btc_price == 0 or usdt_price == 0:
        print("Failed to fetch prices.")
        return

    # === PHASE 1: BUYING (3 days) ===
    if state["status"] == "buying":
        if state["start_price"] == 0.0:
            state["start_price"] = btc_price
        step = state["step"]
        if step < 3:
            if step == 0: pct = 0.33
            elif step == 1: pct = 0.33
            else: pct = 0.34
            
            buy_toman = INITIAL_CAPITAL * pct
            fee_toman = buy_toman * (TOTAL_FEE / 100)
            net_buy = buy_toman - fee_toman
            btc_bought = net_buy / btc_price
            
            state["btc_amount"] += btc_bought
            state["capital"] -= buy_toman
            state["step"] += 1
            
            state["trades"].append({
                "time": now.isoformat(),
                "type": "buy",
                "step": state["step"],
                "price": btc_price,
                "buy_toman": buy_toman,
                "btc_bought": btc_bought
            })
            
            send_bale(f"🟢 M10-Dividend BUY {state['step']}/3 | Price: {btc_price:,.0f} | BTC: {btc_bought:.8f}")
            
            if state["step"] == 3:
                state["status"] = "active"
                state["original_btc"] = state["btc_amount"]
                # Set last_sale_month to current month so first sale is next month
                state["last_sale_month"] = current_month
                send_bale(f"🟢 M10-Dividend ALL BUYS COMPLETED\nTotal BTC: {state['btc_amount']:.8f}\nFirst monthly sale: next month")

    # === PHASE 2: MONTHLY SELL ===
    elif state["status"] == "active":
        if current_month > state["last_sale_month"]:
            # Time to sell
            if state["cumulative_sold"] < MAX_CUMULATIVE_SELL and state["btc_amount"] > 0:
                sell_btc = state["btc_amount"] * MONTHLY_SELL_PCT
                remaining_quota = state["original_btc"] * (MAX_CUMULATIVE_SELL - state["cumulative_sold"])
                sell_btc = min(sell_btc, remaining_quota)
                
                if sell_btc > 0:
                    gross_toman = sell_btc * btc_price
                    fee_toman = gross_toman * (TOTAL_FEE / 100)
                    net_toman = gross_toman - fee_toman
                    usdt_bought = net_toman / usdt_price
                    
                    state["btc_amount"] -= sell_btc
                    state["usdt_amount"] += usdt_bought
                    state["cumulative_sold"] += (sell_btc / state["original_btc"])
                    state["last_sale_month"] = current_month
                    
                    state["trades"].append({
                        "time": now.isoformat(),
                        "type": "sell",
                        "price": btc_price,
                        "btc_sold": sell_btc,
                        "usdt_bought": usdt_bought,
                        "toman_value": net_toman
                    })
                    
                    send_bale(
                        f"💰 M10-Dividend MONTHLY SALE\n"
                        f"BTC sold: {sell_btc:.8f}\n"
                        f"USDT received: {usdt_bought:.2f}\n"
                        f"Toman value: {net_toman:,.0f}\n"
                        f"Total BTC remaining: {state['btc_amount']:.8f}\n"
                        f"Cumulative sold: {state['cumulative_sold']*100:.1f}%"
                    )
        
        # Report current value
        btc_value = state["btc_amount"] * btc_price
        usdt_value = state["usdt_amount"] * usdt_price
        total_value = btc_value + usdt_value
        roi = ((total_value / INITIAL_CAPITAL) - 1) * 100
        print(f"[M10-Dividend] ACTIVE | BTC: {state['btc_amount']:.8f} | USDT: {state['usdt_amount']:.2f} | Value: {total_value:,.0f} | ROI: {roi:+.2f}% | Sold: {state['cumulative_sold']*100:.1f}%")

    state["last_run"] = now.isoformat()
    if save_to_github(STATE_FILE, state, sha):
        print(f"State saved. Status: {state['status']}")

if __name__ == "__main__":
    main()
