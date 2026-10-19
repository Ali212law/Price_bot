#!/usr/bin/env python3
# paper_trade_m9.py — M9 Global Paper Trading (BB + RSI + ATR)
# Assets: ETHUSDT, SUIUSDT, SOLUSDT

import os, json, base64, requests, time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "paper_m9_trades.json"
INITIAL_CAPITAL = 10000.0
RISK_PER_TRADE = 0.005 # 0.5%
MAX_TOTAL_RISK = 0.02  # 2%
TOTAL_FEE = 0.1 # Binance spot fee 0.1%

SYMBOLS = ["ETHUSDT", "SUIUSDT", "SOLUSDT"]
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

def fetch_data(symbol):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit=200"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])} for k in r.json()]
    except: pass
    return []

def calc_indicators(candles):
    closes = [c["c"] for c in candles]
    n = len(closes)
    # RSI 14
    rsi = 50.0
    if n > 14:
        gains, losses = [], []
        for i in range(1, n):
            chg = closes[i] - closes[i-1]
            gains.append(max(chg, 0)); losses.append(max(-chg, 0))
        ag = sum(gains[-14:]) / 14
        al = sum(losses[-14:]) / 14
        rsi = 100 - (100 / (1 + ag/al)) if al > 0 else 100

    # ATR 14
    atr = 0.0
    if n > 14:
        trs = []
        for i in range(1, n):
            trs.append(max(candles[i]["h"] - candles[i]["l"], abs(candles[i]["h"] - closes[i-1]), abs(candles[i]["l"] - closes[i-1])))
        atr = sum(trs[-14:]) / 14

    # Bollinger Lower (20, 2)
    lower_bb = 0.0
    if n >= 20:
        window = closes[-20:]
        sma = sum(window) / 20
        variance = sum((x - sma) ** 2 for x in window) / 20
        std = variance ** 0.5
        lower_bb = sma - (2 * std)
        
    return rsi, atr, lower_bb

def main():
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "trades" not in state:
        state = {"capital": INITIAL_CAPITAL, "trades": []}

    # 1. Update Open Positions
    total_risk = 0.0
    for t in state["trades"]:
        if t["status"] == "open":
            total_risk += (t["risk_pct"] / 100)
            candles = fetch_data(t["symbol"])
            if not candles: continue
            low = candles[-1]['l']
            high = candles[-1]['h']
            
            if low <= t["sl"]:
                pnl_pct = -t["sl_pct"] - TOTAL_FEE
                state["capital"] += (t["amount"] * (pnl_pct / 100))
                t.update({"status": "closed", "exit_reason": "SL", "exit_price": t["sl"], "pnl": pnl_pct})
            elif high >= t["tp"]:
                pnl_pct = t["tp_pct"] - TOTAL_FEE
                state["capital"] += (t["amount"] * (pnl_pct / 100))
                t.update({"status": "closed", "exit_reason": "TP", "exit_price": t["tp"], "pnl": pnl_pct})

    # 2. Check for New Entries
    for symbol in SYMBOLS:
        if any(t["symbol"] == symbol and t["status"] == "open" for t in state["trades"]): continue
        if total_risk >= MAX_TOTAL_RISK: break

        candles = fetch_data(symbol)
        if len(candles) < 50: continue
        
        current_price = candles[-1]['c']
        rsi, atr, lower_bb = calc_indicators(candles)
        
        # E2 Logic: Price <= Lower BB AND RSI < 35
        if lower_bb > 0 and current_price <= lower_bb and rsi < 35 and atr > 0:
            sl_dist = 2 * atr
            sl_pct = (sl_dist / current_price) * 100
            tp_pct = sl_pct * 2 # TP = 2 * SL
            
            # Position Sizing based on Risk
            risk_amount = state["capital"] * RISK_PER_TRADE
            amount = (risk_amount / sl_pct) * 100
            
            entry = {"symbol": symbol, "entry_time": datetime.now(timezone.utc).isoformat(), 
                     "entry_price": current_price, "sl": current_price - sl_dist, 
                     "tp": current_price + (2 * sl_dist), "sl_pct": sl_pct, "tp_pct": tp_pct,
                     "amount": amount, "status": "open", "risk_pct": RISK_PER_TRADE*100}
            
            state["trades"].append(entry)
            total_risk += (RISK_PER_TRADE * 100)
            print(f"OPENED {symbol} | Price: {current_price} | SL: {entry['sl']:.2f} | Size: {amount:.2f} USDT")

    if save_to_github(STATE_FILE, state, sha):
        print(f"State updated. Capital: {state['capital']:.2f} USDT")

if __name__ == "__main__":
    main()
