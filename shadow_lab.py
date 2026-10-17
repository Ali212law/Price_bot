#!/usr/bin/env python3
"""
shadow_lab.py v4.3 — Per-Strategy Independent Accounts
- H1 changed to GlobalSafe (Global sentiment != BEARISH)
- H2 reduced to half size (17,500 Toman)
- H5 uses cross tolerance with previous live price
- G_Hybrid clearly commented
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

STRATEGIES = ["A_FixedTP", "F_WideTrail", "G_Hybrid",
              "H1_GlobalSafe", "H2_USD", "H3_RSI25",
              "H4_EMA200", "H5_BB_LiveCross"]

INITIAL_CAPITAL = 1_000_000.0
RISK_PER_TRADE = 700.0
SL_PCT = 2.0
TP_PCT = 4.0
POS_SIZE = RISK_PER_TRADE / (SL_PCT / 100)   # 35,000 Toman
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

def fetch_data():
    try:
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=10)
        symbols = r.json().get("result", {}).get("symbols", {})
        price = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        if price > 100_000_000_000: price /= 10
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

    bb_lower, bb_prev_close = None, None
    if len(closes) >= 21:
        sma = sum(closes[-20:]) / 20
        var = sum((x - sma)**2 for x in closes[-20:]) / 20
        bb_lower = sma - (var**0.5 * 2)
        bb_prev_close = closes[-1]

    ema200 = None
    try:
        r4 = requests.get("https://api.wallex.ir/v1/udf/history",
                         params={"symbol":"BTCTMN","resolution":"240",
                                 "from": int(time.time())-60*24*3600,"to":int(time.time())}, timeout=10)
        d4 = r4.json()
        if d4.get('s') == 'ok' and len(d4['c']) > 200:
            c4 = [float(x) for x in d4['c']]
            if c4[0] > 100_000_000_000: c4 = [x/10 for x in c4]
            ema = sum(c4[:200])/200
            k = 2/201
            for p in c4[200:]: ema = p*k + ema*(1-k)
            ema200 = ema
    except: pass

    usd_chg = 0.0
    d_h, _ = gh_load(DOLLAR_HISTORY_FILE)
    if d_h and len(d_h) >= 2:
        curr = d_h[-1][1]
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)
        past = [p for t, p in d_h if datetime.fromisoformat(t.replace("Z","")) <= cutoff]
        if past: usd_chg = ((curr - past[0]) / past[0]) * 100

    # Fetch Global News
    g_h, _ = gh_load(NEWS_HISTORY_FILE)
    global_sent = "neutral"
    if g_h:
        global_sent = g_h[-1].get("sentiment", "neutral")

    return {"price": price, "rsi": rsi, "usd_chg": usd_chg, "global_sent": global_sent,
            "ema200": ema200, "bb_lower": bb_lower, "bb_prev_close": bb_prev_close}

def check_exit(trade, current_price, strat):
    entry = trade["entry"]
    if current_price <= entry * (1 - SL_PCT/100):
        return True, entry * (1 - SL_PCT/100), "Hard_SL", -SL_PCT - TOTAL_FEE

    if strat in ["A_FixedTP", "H1_GlobalSafe", "H2_USD", "H3_RSI25", "H4_EMA200", "H5_BB_LiveCross"]:
        if current_price >= entry * (1 + TP_PCT/100):
            return True, entry * (1 + TP_PCT/100), "TP", TP_PCT - TOTAL_FEE

    elif strat == "F_WideTrail":
        trade["max_price"] = max(trade.get("max_price", entry), current_price)
        if current_price >= entry * 1.04: trade["trailing_active"] = True
        if trade.get("trailing_active"):
            trail_sl = max(trade["max_price"] * 0.95, entry * 1.006)
            if current_price <= trail_sl:
                pnl = (trail_sl - entry) / entry * 100 - TOTAL_FEE
                return True, trail_sl, "Trail", pnl

    elif strat == "G_Hybrid":
        # G_Hybrid Logic:
        # 50% of position is sold at Fixed TP (4%).
        # The other 50% stays open with a 5% Wide Trailing Stop.
        # PnL is the average of both halves.
        trade["max_price"] = max(trade.get("max_price", entry), current_price)
        if not trade.get("partial_closed") and current_price >= entry * 1.04:
            trade["partial_closed"] = True
        if trade.get("partial_closed"):
            trail_sl = max(trade["max_price"] * 0.95, entry * 1.006)
            if current_price <= trail_sl:
                trail_pnl = (trail_sl - entry) / entry * 100 - TOTAL_FEE
                avg = ((TP_PCT - TOTAL_FEE) + trail_pnl) / 2
                return True, trail_sl, "Hybrid", avg

    return False, None, None, None

def main():
    print("=== SHADOW LAB v4.3 ===")
    data = fetch_data()
    if not data: return

    price = data["price"]
    ts = datetime.now(timezone.utc).isoformat()
    
    state, sha = gh_load(LAB_FILE)
    if not state or "accounts" not in state:
        state = {"accounts": {s: {"capital": INITIAL_CAPITAL, "trades": []} for s in STRATEGIES},
                 "last_check_utc": ts, "last_live_price": price}
    
    # H5 Tolerance: check if last_live_price was below BB and current is above
    last_price = state.get("last_live_price", price)
    
    notifications = []

    # 1. Process exits
    for strat in STRATEGIES:
        acct = state["accounts"][strat]
        new_trades = []
        for t in acct["trades"]:
            if t["status"] != "open":
                new_trades.append(t); continue
            closed, exit_p, reason, pnl = check_exit(t, price, strat)
            if closed:
                t.update({"status": "closed", "exit_price": exit_p,
                          "exit_reason": reason, "exit_time": ts, "pnl_pct": pnl})
                acct["capital"] += t["reserved"] * (1 + pnl/100)
                notifications.append(f"🔴 [CLOSE] {strat} | {reason} | {pnl:+.2f}%")
            new_trades.append(t)
        acct["trades"] = new_trades[-200:]

    # 2. Process entries
    def try_open(strat, reason, size=POS_SIZE):
        acct = state["accounts"][strat]
        open_cnt = sum(1 for t in acct["trades"] if t["status"] == "open")
        if open_cnt >= MAX_OPEN or acct["capital"] < size: return False
        acct["capital"] -= size
        acct["trades"].append({
            "strategy": strat, "status": "open", "entry": price,
            "entry_time": ts, "max_price": price, "reserved": size,
            "trailing_active": False, "partial_closed": False, "reason": reason
        })
        notifications.append(f"🟢 [OPEN] {strat} @ {price:,.0f} | {reason}")
        return True

    rsi = data["rsi"]
    
    # Base DIP (RSI<30)
    if rsi < 30:
        try_open("A_FixedTP", f"RSI={rsi:.1f}")
        try_open("F_WideTrail", f"RSI={rsi:.1f}")
        try_open("G_Hybrid", f"RSI={rsi:.1f}")
        
    # H1: Global Safe (Global != BEARISH)
    if rsi < 30 and data["global_sent"] != "bearish":
        try_open("H1_GlobalSafe", f"RSI={rsi:.1f}, Global={data['global_sent']}")
        
    # H2: USD Momentum (Half size)
    if data["usd_chg"] > 1.0:
        try_open("H2_USD", f"USD={data['usd_chg']:.2f}%", size=POS_SIZE/2)
        
    # H3: Extreme Dip
    if rsi < 25:
        try_open("H3_RSI25", f"RSI={rsi:.1f}")
        
    # H4: EMA 200 Filter
    if rsi < 30 and data["ema200"] and price > data["ema200"]:
        try_open("H4_EMA200", f"RSI={rsi:.1f}, >EMA200")
        
    # H5: BB Live Cross with tolerance
    if data["bb_lower"] and data["bb_prev_close"]:
        if last_price < data["bb_lower"] and price > data["bb_lower"]:
            try_open("H5_BB_LiveCross", "Crossed above Lower BB")

    state["last_check_utc"] = ts
    state["last_live_price"] = price
    gh_save(LAB_FILE, state, sha)

    # 3. Send Aggregated Bale Message
    if notifications:
        msg = f"🧪 Shadow Lab Update\n\n" + "\n".join(notifications) + f"\n\n💰 Price: {price:,.0f}"
        send_bale(msg)
        print(f"Sent {len(notifications)} notifications to Bale.")

    # 4. Print Summary
    print(f"\nPrice: {price:,.0f} | RSI={rsi:.1f} | USD={data['usd_chg']:.2f}% | Global={data['global_sent']}")
    print(f"{'Strategy':<16} {'Free':>10} {'Equity':>12} {'Trd':>4} {'WR':>6}")
    print("-" * 50)
    for s in STRATEGIES:
        acct = state["accounts"][s]
        closed = [t for t in acct["trades"] if t["status"] == "closed"]
        opens = [t for t in acct["trades"] if t["status"] == "open"]
        equity = acct["capital"] + sum(t["reserved"] * (price / t["entry"]) for t in opens)
        wins = sum(1 for t in closed if t.get("pnl_pct", 0) > 0)
        wr = (wins/len(closed)*100) if closed else 0
        print(f"{s:<16} {acct['capital']:>10,.0f} {equity:>12,.0f} {len(closed):>4} {wr:>5.1f}%")

if __name__ == "__main__":
    main()
