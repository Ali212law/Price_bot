#!/usr/bin/env python3
"""
paper_trade_m8.py — M8 Global Market Paper Trading
- Uses Binance Vision Data (1H candles).
- Matrix: SOL(DIP/Breakout), ETH(DIP), XRP(Breakout), BTC(Breakout+ATR).
- Risk Management: Max 0.5% risk per trade, Max 2% total risk.
"""
import os, json, base64, requests, time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
STATE_FILE = "paper_m8_trades.json"
INITIAL_CAPITAL = 10000.0
RISK_PER_TRADE = 0.005 # 0.5%
MAX_TOTAL_RISK = 0.02  # 2%
TOTAL_FEE = 0.1 # 0.1% Binance spot fee per side

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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

def calculate_indicators(candles):
    closes = [c['c'] for c in candles]
    vols = [c['v'] for c in candles]
    
    # RSI 14
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

    # ATR 14
    atr = 0.0
    if len(candles) > 14:
        trs = []
        for i in range(1, len(candles)):
            tr = max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - closes[i-1]), abs(candles[i]['l'] - closes[i-1]))
            trs.append(tr)
        atr = sum(trs[-14:]) / 14

    # Breakout High 20
    high_20 = max([c['h'] for c in candles[-21:-1]]) if len(candles) > 21 else 0
    avg_vol_20 = sum(vols[-21:-1]) / 20 if len(candles) > 21 else 0
    
    return rsi, atr, high_20, avg_vol_20

def main():
    state, sha = load_from_github(STATE_FILE)
    
    # رفع باگ: مقداردهی اولیه صحیح در صورت خالی بودن فایل یا نبود کلید
    if not isinstance(state, dict) or "trades" not in state:
        state = {"capital": INITIAL_CAPITAL, "trades": []}
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

    # 1. Update Open Positions
    total_risk = 0.0
    for t in state["trades"]:
        if t["status"] == "open":
            total_risk += (t["risk_pct"] / 100)
            candles = fetch_data(t["symbol"])
            if not candles: continue
            low = candles[-1]['l']
            high = candles[-1]['h']
            
            # Check SL/TP
            if low <= t["sl"]:
                pnl_pct = -t["sl_pct"] - TOTAL_FEE
                state["capital"] += (t["amount"] * (pnl_pct / 100))
                t.update({"status": "closed", "exit_reason": "SL", "exit_price": t["sl"], "pnl": pnl_pct})
            elif high >= t["tp"]:
                pnl_pct = t["tp_pct"] - TOTAL_FEE
                state["capital"] += (t["amount"] * (pnl_pct / 100))
                t.update({"status": "closed", "exit_reason": "TP", "exit_price": t["tp"], "pnl": pnl_pct})

    # 2. Check for New Entries
    for symbol in symbols:
        # Skip if already open for this symbol
        if any(t["symbol"] == symbol and t["status"] == "open" for t in state["trades"]): continue
        
        # Risk limit check
        if total_risk >= MAX_TOTAL_RISK: break

        candles = fetch_data(symbol)
        if len(candles) < 50: continue
        
        current_price = candles[-1]['c']
        current_vol = candles[-1]['v']
        rsi, atr, high_20, avg_vol = calculate_indicators(candles)
        
        triggered = False
        sl_pct = 2.0
        tp_pct = 4.0
        
        if symbol == "SOLUSDT":
            if rsi < 30: triggered = True # DIP
            elif current_price > high_20 and current_vol > avg_vol * 1.5: triggered = True # Breakout
        elif symbol == "ETHUSDT":
            if rsi < 30: triggered = True # DIP
        elif symbol in ["XRPUSDT", "BTCUSDT"]:
            if current_price > high_20 and current_vol > avg_vol * 1.5: triggered = True # Breakout
            if symbol == "BTCUSDT" and atr > 0:
                sl_pct = (atr * 2.0 / current_price) * 100 # ATR 2.0x
                sl_pct = max(1.0, min(5.0, sl_pct))

        if triggered:
            # Position Sizing based on Risk
            risk_amount = state["capital"] * RISK_PER_TRADE
            amount = (risk_amount / sl_pct) * 100
            
            entry = {"symbol": symbol, "entry_time": datetime.now(timezone.utc).isoformat(), 
                     "entry_price": current_price, "sl": current_price*(1-sl_pct/100), 
                     "tp": current_price*(1+tp_pct/100), "sl_pct": sl_pct, "tp_pct": tp_pct,
                     "amount": amount, "status": "open", "risk_pct": RISK_PER_TRADE*100}
            
            state["trades"].append(entry)
            total_risk += (RISK_PER_TRADE * 100)
            print(f"OPENED {symbol} | Price: {current_price} | Size: {amount:.2f} USDT")

    if save_to_github(STATE_FILE, state, sha):
        print(f"State updated. Capital: {state['capital']:.2f} USDT")

if __name__ == "__main__":
    main()
