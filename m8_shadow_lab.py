#!/usr/bin/env python3
# m8_shadow_lab.py — Global Shadow Lab (Keltner, VWAP, MACD)
import os, json, base64, requests, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
STATE_FILE = "m8_shadow_trades.json"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INITIAL_CAPITAL = 1000.0
TOTAL_FEE = 0.1
HEADERS = {"User-Agent": "Mozilla/5.0"}

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
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = session.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def fetch_data(symbol):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit=200"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in r.json()]
    except: pass
    return []

def calc_ema(data, period):
    if len(data) < period: return [0]*len(data)
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    out = [0]*(period-1) + [e]
    for price in data[period:]:
        e = price * k + e * (1 - k)
        out.append(e)
    return out

def calc_atr(candles, period=10):
    n = len(candles)
    atr = [0.0] * n
    if n <= period: return atr
    trs = []
    for i in range(1, n):
        tr = max(candles[i]["h"] - candles[i]["l"], abs(candles[i]["h"] - candles[i-1]["c"]), abs(candles[i]["l"] - candles[i-1]["c"]))
        trs.append(tr)
        if i >= period: atr[i] = sum(trs[-period:]) / period
    return atr

def calc_vwap(candles, period=24):
    vwap = [0.0] * len(candles)
    for i in range(period - 1, len(candles)):
        typical_prices = [(c["h"] + c["l"] + c["c"]) / 3 for c in candles[i-period+1:i+1]]
        volumes = [c["v"] for c in candles[i-period+1:i+1]]
        total_v = sum(volumes)
        if total_v > 0:
            vwap[i] = sum(tp * vol for tp, vol in zip(typical_prices, volumes)) / total_v
    return vwap

def calc_macd(closes):
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd = [e12 - e26 if e12 > 0 and e26 > 0 else 0 for e12, e26 in zip(ema12, ema26)]
    signal = calc_ema(macd, 9)
    return macd, signal

def main():
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "accounts" not in state:
        state = {"accounts": {
            "KELTNER": {"cap": INITIAL_CAPITAL, "trades": []},
            "VWAP": {"cap": INITIAL_CAPITAL, "trades": []},
            "MACD": {"cap": INITIAL_CAPITAL, "trades": []}
        }}
    now_ts = int(time.time())
    for symbol in SYMBOLS:
        candles = fetch_data(symbol)
        if len(candles) < 50: continue
        closes = [c["c"] for c in candles]
        current_price = closes[-1]
        ema20 = calc_ema(closes, 20)
        atr10 = calc_atr(candles, 10)
        vwap = calc_vwap(candles, 24)
        macd, macd_signal = calc_macd(closes)
        for strat_name, acc in state["accounts"].items():
            for t in acc["trades"]:
                if t["status"] == "open" and t["symbol"] == symbol:
                    c = candles[-1]
                    if c["l"] <= t["sl"]:
                        pnl = -t["sl_pct"] - TOTAL_FEE
                        acc["cap"] += (t["amount"] * (pnl/100))
                        t.update({"status": "closed", "reason": "SL", "pnl": pnl})
                    elif c["h"] >= t["tp"]:
                        pnl = t["tp_pct"] - TOTAL_FEE
                        acc["cap"] += (t["amount"] * (pnl/100))
                        t.update({"status": "closed", "reason": "TP", "pnl": pnl})
            has_open = any(t["status"] == "open" and t["symbol"] == symbol for t in acc["trades"])
            if has_open: continue
            triggered = False
            sl_p, tp_p = 2.0, 4.0
            if atr10[-1] > 0:
                sl_dist = 2 * atr10[-1]
                sl_p = (sl_dist / current_price) * 100
                tp_p = sl_p * 2
            if strat_name == "KELTNER":
                lower_keltner = ema20[-1] - (2 * atr10[-1])
                if current_price <= lower_keltner: triggered = True
            elif strat_name == "VWAP":
                if vwap[-1] > 0 and current_price <= (vwap[-1] * 0.98): triggered = True
            elif strat_name == "MACD":
                if macd[-1] > macd_signal[-1] and macd[-2] <= macd_signal[-2]: triggered = True
            if triggered:
                amount = acc["cap"] * 0.1
                t = {"symbol": symbol, "entry": current_price, "entry_ts": now_ts, "sl": current_price - (current_price * sl_p / 100), "tp": current_price + (current_price * tp_p / 100), "sl_pct": sl_p, "tp_pct": tp_p, "amount": amount, "status": "open"}
                acc["trades"].append(t)
                print(f"[{strat_name}] OPENED {symbol} at {current_price}")
    if save_to_github(STATE_FILE, state, sha):
        print("M8 Shadow Lab updated.")

if __name__ == "__main__":
    main()
