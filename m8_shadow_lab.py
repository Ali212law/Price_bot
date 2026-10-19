#!/usr/bin/env python3
"""
m8_shadow_lab.py — Global Shadow Lab (Binance 1H)
- Runs key strategies on BTC, ETH, SOL, XRP. (H6 is quarantined).
"""
import os, json, base64, requests, time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "m8_shadow_trades.json"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INITIAL_CAPITAL = 1000.0
TOTAL_FEE = 0.1

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
            return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in r.json()]
    except: pass
    return []

def calc_indicators(candles):
    closes = [c['c'] for c in candles]
    rsi = 50.0
    if len(closes) > 14:
        gains, losses = [], []
        for i in range(1, len(closes)):
            ch = closes[i] - closes[i-1]
            gains.append(ch if ch > 0 else 0)
            losses.append(abs(ch) if ch < 0 else 0)
        ag = sum(gains[-14:]) / 14
        al = sum(losses[-14:]) / 14
        rsi = 100 - (100 / (1 + ag/al)) if al > 0 else 100
    atr = 0.0
    if len(candles) > 14:
        trs = []
        for i in range(1, len(candles)):
            trs.append(max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - closes[i-1]), abs(candles[i]['l'] - closes[i-1])))
        atr = sum(trs[-14:]) / 14
    return rsi, atr

def main():
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "accounts" not in state:
        # H6 حذف شد (قرنطینه)
        state = {"accounts": {
            "A_FixedTP": {"cap": INITIAL_CAPITAL, "trades": []},
            "F_WideTrail": {"cap": INITIAL_CAPITAL, "trades": []},
            "G_Hybrid": {"cap": INITIAL_CAPITAL, "trades": []},
            "H3_RSI25": {"cap": INITIAL_CAPITAL, "trades": []},
            "H10_SESSION": {"cap": INITIAL_CAPITAL, "trades": []},
            "H11_TIMEEXIT_48H": {"cap": INITIAL_CAPITAL, "trades": []}
        }}

    now_ts = int(time.time())
    
    for symbol in SYMBOLS:
        candles = fetch_data(symbol)
        if len(candles) < 50: continue
        current_price = candles[-1]['c']
        current_ts = candles[-1]['t'] / 1000
        rsi, atr = calc_indicators(candles)
        
        dt = datetime.fromtimestamp(current_ts, tz=timezone.utc)
        
        for strat_name, acc in state["accounts"].items():
            # 1. بررسی خروج
            for t in acc["trades"]:
                if t["status"] == "open" and t["symbol"] == symbol:
                    if candles[-1]['l'] <= t["sl"]:
                        pnl = -t["sl_pct"] - TOTAL_FEE
                        acc["cap"] += (t["amount"] * (pnl/100))
                        t.update({"status": "closed", "reason": "SL", "pnl": pnl})
                    elif candles[-1]['h'] >= t["tp"]:
                        pnl = t["tp_pct"] - TOTAL_FEE
                        acc["cap"] += (t["amount"] * (pnl/100))
                        t.update({"status": "closed", "reason": "TP", "pnl": pnl})
                    elif strat_name == "H11_TIMEEXIT_48H" and (now_ts - t["entry_ts"]) > 48*3600:
                        pnl = ((current_price - t["entry"])/t["entry"]*100) - TOTAL_FEE
                        acc["cap"] += (t["amount"] * (pnl/100))
                        t.update({"status": "closed", "reason": "TimeExit", "pnl": pnl})

            # 2. بررسی ورود
            has_open = any(t["status"] == "open" and t["symbol"] == symbol for t in acc["trades"])
            if has_open: continue
            
            triggered = False
            sl_p, tp_p = 2.0, 4.0
            
            if strat_name == "A_FixedTP" and rsi < 30: triggered = True
            elif strat_name == "F_WideTrail" and rsi < 30: triggered = True 
            elif strat_name == "G_Hybrid" and rsi < 30: triggered = True
            elif strat_name == "H3_RSI25" and rsi < 25: triggered = True
            elif strat_name == "H10_SESSION" and rsi < 30:
                if not (18 <= dt.hour < 24): triggered = True
            elif strat_name == "H11_TIMEEXIT_48H" and rsi < 30: triggered = True
            
            if triggered:
                amount = acc["cap"] * 0.1
                t = {
                    "symbol": symbol, "entry": current_price, "entry_ts": now_ts,
                    "sl": current_price*(1-sl_p/100), "tp": current_price*(1+tp_p/100),
                    "sl_pct": sl_p, "tp_pct": tp_p, "amount": amount, "status": "open"
                }
                acc["trades"].append(t)
                print(f"[{strat_name}] OPENED {symbol} at {current_price}")

    if save_to_github(STATE_FILE, state, sha):
        print("M8 Shadow Lab state updated.")

if __name__ == "__main__":
    main()
