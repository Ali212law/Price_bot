#!/usr/bin/env python3
"""
shadow_lab.py v5.3 — FIXED: Added bb_lower and bb_prev_close to data dict
"""
import requests, json, os, base64, time
from datetime import datetime, timezone, timedelta

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = "Ali212law/Price_bot"
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "")

LAB_FILE = "shadow_lab_trades.json"
BTC_HISTORY_FILE = "btc_history.json"
DOLLAR_HISTORY_FILE = "dollar_history.json"
NEWS_HISTORY_FILE = "news_history.json"

STRATEGIES_ACTIVE = [
    "A_FixedTP", "F_WideTrail", "G_Hybrid", 
    "H1_GlobalSafe", "H3_RSI25", "H5_BB_LiveCross",
    "H6_ATR_STOP", "H8_DOLLAR_FILTER", "H9_RSI25_CHG", 
    "H10_SESSION", "H11_TIMEEXIT_48H"
]

STRATEGIES_ARCHIVED = ["H2_USD", "H4_EMA200"]

INITIAL_CAPITAL = 1_000_000.0
RISK_PER_TRADE = 700.0
POS_SIZE = RISK_PER_TRADE / 0.02
MAX_OPEN = 1
TOTAL_FEE = 0.6

def send_bale(msg):
    if not BALE_TOKEN or not BALE_CHAT_ID: return
    try:
        requests.post(f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage", 
                      json={"chat_id": BALE_CHAT_ID, "text": msg}, timeout=10)
    except: pass

def gh_load(fn):
    try:
        r = requests.get(f"https://api.github.com/repos/{GH_REPO}/contents/{fn}",
                         headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return json.loads(base64.b64decode(d["content"]).decode()), d["sha"]
    except: pass
    return None, None

def gh_save(fn, data, sha=None):
    try:
        c = base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
        p = {"message": f"Update {fn}", "content": c}
        if sha: p["sha"] = sha
        r = requests.put(f"https://api.github.com/repos/{GH_REPO}/contents/{fn}",
                         headers={"Authorization": f"token {GH_TOKEN}"}, json=p, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def calculate_atr(candles, period=14):
    if len(candles) < period + 1: return 0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['h']
        l = candles[i]['l']
        pc = candles[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else 0

def fetch_data():
    try:
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=10)
        symbols = r.json().get("result", {}).get("symbols", {})
        price = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        if price > 100_000_000_000: price /= 10

        r_ohlc = requests.get("https://api.wallex.ir/v1/udf/history", 
                              params={"symbol":"BTCTMN", "resolution":"15", 
                                      "from": int(time.time())-24*3600, "to": int(time.time())}, timeout=10)
        ohlc_data = r_ohlc.json()
        candles = []
        if ohlc_data.get('s') == 'ok':
            for i in range(len(ohlc_data['t'])):
                c = float(ohlc_data['c'][i])
                if c > 100_000_000_000: c /= 10
                candles.append({
                    "h": float(ohlc_data['h'][i])/(10 if float(ohlc_data['h'][i])>100_000_000_000 else 1),
                    "l": float(ohlc_data['l'][i])/(10 if float(ohlc_data['l'][i])>100_000_000_000 else 1),
                    "c": c
                })
        atr_val = calculate_atr(candles, 14)
    except: return None

    btc_h, _ = gh_load(BTC_HISTORY_FILE)
    btc_h = btc_h or []
    closes = [p for t, p in btc_h]

    rsi = 50.0
    if len(closes) >= 15:
        g, l = [], []
        for i in range(1, len(closes)):
            ch = closes[i] - closes[i-1]
            if ch > 0: g.append(ch); l.append(0)
            else: g.append(0); l.append(abs(ch))
        ag, al = sum(g[-14:])/14, sum(l[-14:])/14
        rsi = 100 - (100/(1+ag/al)) if al > 0 else 100
        
    chg24h = ((price - closes[-96]) / closes[-96]) * 100 if len(closes) >= 96 else 0

    # --- FIX: Calculate Bollinger Bands ---
    bb_lower = None
    bb_prev_close = None
    if len(closes) >= 21:
        sma = sum(closes[-20:]) / 20
        var = sum((x - sma)**2 for x in closes[-20:]) / 20
        bb_lower = sma - (var**0.5 * 2)
        bb_prev_close = closes[-1]
    # --------------------------------------

    usd_chg = 0.0
    d_h, _ = gh_load(DOLLAR_HISTORY_FILE)
    if d_h and len(d_h) >= 2:
        curr = d_h[-1][1]
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)
        past = [p for t, p in d_h if datetime.fromisoformat(t.replace("Z","")) <= cutoff]
        if past: usd_chg = ((curr - past[0]) / past[0]) * 100

    g_h, _ = gh_load(NEWS_HISTORY_FILE)
    global_sent = "neutral"
    if g_h: global_sent = g_h[-1].get("sentiment", "neutral")

    return {"price": price, "rsi": rsi, "chg24h": chg24h, "usd_chg": usd_chg, 
            "global_sent": global_sent, "atr": atr_val,
            "bb_lower": bb_lower, "bb_prev_close": bb_prev_close}

def check_exit(trade, current_price, strat, now_utc):
    entry = trade["entry"]
    sl_pct = trade.get("custom_sl", 2.0)
    tp_pct = trade.get("custom_tp", 4.0)
    
    if current_price <= entry * (1 - sl_pct/100):
        return True, entry * (1 - sl_pct/100), "Hard_SL", -sl_pct - TOTAL_FEE

    if strat in ["A_FixedTP", "H1_GlobalSafe", "H3_RSI25", "H6_ATR_STOP", "H8_DOLLAR_FILTER", "H9_RSI25_CHG", "H10_SESSION", "H11_TIMEEXIT_48H"]:
        if current_price >= entry * (1 + tp_pct/100):
            return True, entry * (1 + tp_pct/100), "TP", tp_pct - TOTAL_FEE

    if strat == "H11_TIMEEXIT_48H":
        entry_dt = datetime.fromisoformat(trade["entry_time"].replace("Z", "+00:00"))
        hours_held = (now_utc - entry_dt).total_seconds() / 3600
        if hours_held >= 48:
            pnl = (current_price - entry) / entry * 100 - TOTAL_FEE
            return True, current_price, "Time_Exit_48h", pnl

    elif strat == "F_WideTrail":
        trade["max_price"] = max(trade.get("max_price", entry), current_price)
        if current_price >= entry * 1.04: trade["trailing_active"] = True
        if trade.get("trailing_active"):
            trail_sl = max(trade["max_price"] * 0.95, entry * 1.006)
            if current_price <= trail_sl:
                pnl = (trail_sl - entry) / entry * 100 - TOTAL_FEE
                return True, trail_sl, "Trail", pnl

    elif strat == "G_Hybrid":
        trade["max_price"] = max(trade.get("max_price", entry), current_price)
        if not trade.get("partial_closed") and current_price >= entry * 1.04:
            trade["partial_closed"] = True
        if trade.get("partial_closed"):
            trail_sl = max(trade["max_price"] * 0.95, entry * 1.006)
            if current_price <= trail_sl:
                trail_pnl = (trail_sl - entry) / entry * 100 - TOTAL_FEE
                avg = ((tp_pct - TOTAL_FEE) + trail_pnl) / 2
                return True, trail_sl, "Hybrid", avg

    return False, None, None, None

def main():
    print("=== SHADOW LAB v5.3 ===")
    data = fetch_data()
    if not data: return

    price = data["price"]
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.isoformat()
    hour_utc = now_utc.hour
    
    state, sha = gh_load(LAB_FILE)
    if not state or "accounts" not in state:
        state = {"accounts": {}, "last_check_utc": ts, "last_live_price": price}
    
    for s in STRATEGIES_ACTIVE + STRATEGIES_ARCHIVED:
        if s not in state["accounts"]:
            state["accounts"][s] = {"capital": INITIAL_CAPITAL, "trades": []}
    
    notifications = []

    for strat in STRATEGIES_ACTIVE:
        acct = state["accounts"][strat]
        new_trades = []
        for t in acct["trades"]:
            if t["status"] != "open":
                new_trades.append(t); continue
            
            closed, exit_p, reason, pnl = check_exit(t, price, strat, now_utc)
            if closed:
                t.update({"status": "closed", "exit_price": exit_p,
                          "exit_reason": reason, "exit_time": ts, "pnl_pct": pnl})
                acct["capital"] += t["reserved"] * (1 + pnl/100)
                notifications.append(f"🔴 [CLOSE] {strat} | {reason} | {pnl:+.2f}%")
            new_trades.append(t)
        acct["trades"] = new_trades[-200:]

    def try_open(strat, reason, custom_sl=2.0, custom_tp=4.0, size=POS_SIZE):
        acct = state["accounts"][strat]
        open_cnt = sum(1 for t in acct["trades"] if t["status"] == "open")
        if open_cnt >= MAX_OPEN or acct["capital"] < size: return False
        acct["capital"] -= size
        acct["trades"].append({
            "strategy": strat, "status": "open", "entry": price,
            "entry_time": ts, "max_price": price, "reserved": size,
            "trailing_active": False, "partial_closed": False, "reason": reason,
            "custom_sl": custom_sl, "custom_tp": custom_tp
        })
        notifications.append(f"🟢 [OPEN] {strat} @ {price:,.0f} | {reason}")
        return True

    rsi = data["rsi"]
    
    if rsi < 30:
        try_open("A_FixedTP", f"RSI={rsi:.1f}")
        try_open("F_WideTrail", f"RSI={rsi:.1f}")
        try_open("G_Hybrid", f"RSI={rsi:.1f}")
        try_open("H10_SESSION", f"RSI={rsi:.1f}, Hour={hour_utc}")
        try_open("H11_TIMEEXIT_48H", f"RSI={rsi:.1f}")
    
    if rsi < 30 and data["global_sent"] != "bearish":
        try_open("H1_GlobalSafe", f"RSI={rsi:.1f}, Global={data['global_sent']}")
        
    if rsi < 25:
        try_open("H3_RSI25", f"RSI={rsi:.1f}")
        
    if rsi < 30:
        atr = data["atr"]
        if atr > 0:
            sl_pct = (atr * 1.5 / price) * 100
            sl_pct = max(1.5, min(3.0, sl_pct))
            tp_pct = sl_pct * 2
            try_open("H6_ATR_STOP", f"RSI={rsi:.1f}, ATR={atr:,.0f}", custom_sl=sl_pct, custom_tp=tp_pct)

    if rsi < 30 and abs(data["usd_chg"]) < 0.5:
        try_open("H8_DOLLAR_FILTER", f"RSI={rsi:.1f}, USD={data['usd_chg']:.2f}%")

    if rsi < 25 and -2.0 <= data["chg24h"] <= -1.5:
        try_open("H9_RSI25_CHG", f"RSI={rsi:.1f}, chg24={data['chg24h']:.2f}%")

    if data["bb_lower"] and data["bb_prev_close"]:
        if state.get("last_live_price", price) < data["bb_lower"] and price > data["bb_lower"]:
            try_open("H5_BB_LiveCross", "Crossed above Lower BB")

    state["last_check_utc"] = ts
    state["last_live_price"] = price
    gh_save(LAB_FILE, state, sha)

    if notifications:
        msg = f"🧪 Shadow Lab Update\n\n" + "\n".join(notifications) + f"\n\n💰 Price: {price:,.0f}"
        send_bale(msg)

    print(f"\nPrice: {price:,.0f} | RSI={rsi:.1f} | chg24={data['chg24h']:.2f}% | USD={data['usd_chg']:.2f}%")
    print(f"{'Strategy':<18} {'Free':>10} {'Equity':>12} {'Trd':>4} {'WR':>6} {'Avg':>7}")
    print("-" * 65)
    
    all_strats = STRATEGIES_ACTIVE + STRATEGIES_ARCHIVED
    has_15_trades = False
    for s in all_strats:
        acct = state["accounts"][s]
        closed = [t for t in acct["trades"] if t["status"] == "closed"]
        opens = [t for t in acct["trades"] if t["status"] == "open"]
        
        if len(closed) >= 15 and s in STRATEGIES_ACTIVE:
            has_15_trades = True
            
        equity = acct["capital"] + sum(t["reserved"] * (price / t["entry"]) for t in opens)
        wins = sum(1 for t in closed if t.get("pnl_pct", 0) > 0)
        wr = (wins/len(closed)*100) if closed else 0
        avg = sum(t.get("pnl_pct", 0) for t in closed) / len(closed) if closed else 0
        
        status = "ARCHIVED" if s in STRATEGIES_ARCHIVED else ""
        print(f"{s:<18} {acct['capital']:>10,.0f} {equity:>12,.0f} {len(closed):>4} {wr:>5.1f}% {avg:>+6.2f}% {status}")

    if has_15_trades:
        print("\n🚨 AI2 REPORT: At least one active strategy hit 15 closed trades! Report required.")

if __name__ == "__main__":
    main()
