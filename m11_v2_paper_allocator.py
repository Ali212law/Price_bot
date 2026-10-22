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
GRID_FILE = "grid_signals.json"

INITIAL_CAPITAL = 10000.0
MAX_ASSET_RISK_PCT = 0.01       # 1% max risk per asset direction (D-88)
MAX_PORTFOLIO_RISK_PCT = 0.025  # 2.5% max total portfolio risk (D-2026-10-22-29)
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

def get_total_asset_risk(state, symbol):
    total_risk = 0.0
    for pos in state["open_positions"]:
        if pos["symbol"] == symbol:
            total_risk += pos.get("risk_amount", 0.0)
    return total_risk

def get_total_portfolio_risk(state):
    return sum(p.get("risk_amount", 0.0) for p in state["open_positions"])

def normalize_entry_time(t):
    if isinstance(t, str):
        try:
            dt = datetime.fromisoformat(t)
            return int(dt.timestamp() * 1000)
        except:
            try: return int(float(t))
            except: return str(t)
    elif isinstance(t, (int, float)):
        return int(t)
    return str(t)

def make_signal_id(strategy, entry_time, symbol):
    return f"{strategy}_{symbol}_{normalize_entry_time(entry_time)}"

def log_rejected_signal(state, signal_data, reason):
    rejected_entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "strategy": signal_data.get("strategy"),
        "symbol": signal_data.get("symbol"),
        "entry_time": signal_data.get("entry_time"),
        "reason": reason,
        "risk_requested": signal_data.get("risk_amount"),
    }
    state["rejected_signals"].append(rejected_entry)
    if len(state["rejected_signals"]) > 200:
        state["rejected_signals"] = state["rejected_signals"][-200:]

def reconcile_positions(state, m9_data, ll_data, vsb_data, grid_data):
    for pos in state["open_positions"][:]:
        source_strat = pos["strategy"]
        source_entry_time = pos["entry_time"]
        source_symbol = pos["symbol"]
        closed_external = False
        exit_price = 0.0
        
        if source_strat == "M9" and isinstance(m9_data, dict):
            for t in m9_data.get("trades", []):
                if normalize_entry_time(t["entry_time"]) == source_entry_time and t["symbol"] == source_symbol and t.get("status") == "closed":
                    closed_external = True
                    exit_price = t["exit_price"]
                    break
        elif source_strat == "LL" and isinstance(ll_data, dict):
            for t in ll_data.get("trades", []):
                if normalize_entry_time(t["entry_time"]) == source_entry_time and t["symbol"] == source_symbol and t.get("status") == "closed":
                    closed_external = True
                    exit_price = t["exit_price"]
                    break
        elif source_strat == "VSB" and isinstance(vsb_data, dict):
            for s in vsb_data.get("signals", []):
                if normalize_entry_time(s["entry_time"]) == source_entry_time and s["symbol"] == source_symbol and s.get("status") == "closed":
                    closed_external = True
                    exit_price = s["exit_price"]
                    break
        elif source_strat == "GRID" and isinstance(grid_data, dict):
            for g in grid_data.get("signals", []):
                if normalize_entry_time(g["entry_time"]) == source_entry_time and g["symbol"] == source_symbol and g.get("status") == "closed":
                    closed_external = True
                    exit_price = g["exit_price"]
                    break
                    
        if closed_external:
            pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            net_pnl = (pos["allocated_capital"] * pnl_pct) - (pos["allocated_capital"] * 0.002)
            state["capital"] += net_pnl
            
            recon_entry = {
                "time": datetime.now(timezone.utc).isoformat(),
                "strategy": source_strat,
                "symbol": source_symbol,
                "exit_price": exit_price,
                "pnl": round(net_pnl, 4)
            }
            state["reconciliation_history"].append(recon_entry)
            if len(state["reconciliation_history"]) > 200:
                state["reconciliation_history"] = state["reconciliation_history"][-200:]
            
            emoji = "🟢" if net_pnl > 0 else "🔴"
            send_bale(f"{emoji} M11-V2 RECONCILED | {source_strat} on {source_symbol} | PnL: {net_pnl:.2f} USDT")
            state["open_positions"].remove(pos)

def try_add_position(state, strategy, symbol, entry_time, entry_price, sl, tp, weight, risk_pct_per_trade, regime, adx, initial_entry=None):
    norm_time = normalize_entry_time(entry_time)
    signal_id = make_signal_id(strategy, norm_time, symbol)
    
    if any(p.get("signal_id") == signal_id for p in state["open_positions"]):
        return False
        
    risk_per_unit = entry_price - sl
    if risk_per_unit <= 0:
        return False
        
    base_risk = state["capital"] * weight * risk_pct_per_trade
    
    current_asset_risk = get_total_asset_risk(state, symbol)
    max_asset_allowed = state["capital"] * MAX_ASSET_RISK_PCT
    if current_asset_risk + base_risk > max_asset_allowed:
        base_risk = max_asset_allowed - current_asset_risk
        if base_risk <= 0:
            log_rejected_signal(state, {"strategy": strategy, "symbol": symbol, "entry_time": norm_time, "risk_amount": base_risk}, "PER_ASSET_CAP_EXCEEDED")
            return False
    
    current_portfolio_risk = get_total_portfolio_risk(state)
    max_portfolio_allowed = state["capital"] * MAX_PORTFOLIO_RISK_PCT
    if current_portfolio_risk + base_risk > max_portfolio_allowed:
        base_risk = max_portfolio_allowed - current_portfolio_risk
        if base_risk <= 0:
            log_rejected_signal(state, {"strategy": strategy, "symbol": symbol, "entry_time": norm_time, "risk_amount": base_risk}, "PORTFOLIO_CAP_EXCEEDED")
            return False
    
    size = base_risk / risk_per_unit
    allocated_capital = size * entry_price
    
    pos = {
        "strategy": strategy,
        "symbol": symbol,
        "entry_time": norm_time,
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "risk_amount": base_risk,
        "allocated_capital": allocated_capital,
        "signal_id": signal_id,
        "regime_at_entry": regime,
        "adx_at_entry": adx
    }
    if initial_entry is not None:
        pos["initial_entry"] = initial_entry
        
    state["open_positions"].append(pos)
    
    send_bale(f"🔵 M11-V2 OPENED | {strategy} on {symbol} | Risk: {base_risk:.2f} USDT | Regime: {regime}")
    return True

def main():
    state, sha = load_from_github(STATE_FILE)
    if not isinstance(state, dict) or "capital" not in state:
        state = {
            "capital": INITIAL_CAPITAL, 
            "open_positions": [], 
            "history": [],
            "rejected_signals": [],
            "reconciliation_history": []
        }
        
    if "rejected_signals" not in state: state["rejected_signals"] = []
    if "reconciliation_history" not in state: state["reconciliation_history"] = []
    
    # Backfill legacy positions - FIX: Always normalize entry_time and force overwrite signal_id
    for pos in state["open_positions"]:
        pos["entry_time"] = normalize_entry_time(pos.get("entry_time", 0))
        pos["signal_id"] = make_signal_id(pos["strategy"], pos["entry_time"], pos["symbol"])
        if "risk_amount" not in pos:
            if pos["strategy"] in ["M9", "VSB"]:
                risk_per_unit = pos["entry_price"] - pos["sl"]
                pos["risk_amount"] = risk_per_unit * (pos["allocated_capital"] / pos["entry_price"])
            elif pos["strategy"] == "LL":
                pos["risk_amount"] = pos["allocated_capital"] * 0.02
            elif pos["strategy"] == "GRID":
                risk_per_unit = pos["entry_price"] - (pos.get("initial_entry", pos["entry_price"]) * 0.90)
                pos["risk_amount"] = risk_per_unit * (pos["allocated_capital"] / pos["entry_price"])
            else:
                pos["risk_amount"] = pos["allocated_capital"] * 0.01
                
    m9_data, _ = load_from_github(M9_FILE)
    ll_data, _ = load_from_github(LL_FILE)
    vsb_data, _ = load_from_github(VSB_FILE)
    grid_data, _ = load_from_github(GRID_FILE)
    
    reconcile_positions(state, m9_data, ll_data, vsb_data, grid_data)
    
    btc_daily = fetch_klines("BTCUSDT", "1d", 50)
    if not btc_daily: return
    adx = calculate_daily_adx(btc_daily)
    
    if adx > 25:
        regime = "TREND"
        w_m9, w_vsb, w_ll, w_grid = 0.1, 0.2, 0.5, 0.2
    elif adx < 20:
        regime = "RANGE"
        w_m9, w_vsb, w_ll, w_grid = 0.3, 0.2, 0.1, 0.4
    else:
        regime = "NEUTRAL"
        w_m9, w_vsb, w_ll, w_grid = 0.25, 0.25, 0.25, 0.25

    # GRID DYNAMIC UPDATE
    if isinstance(grid_data, dict):
        for pos in state["open_positions"]:
            if pos["strategy"] == "GRID":
                g = next((x for x in grid_data.get("signals", []) if normalize_entry_time(x["entry_time"]) == pos["entry_time"] and x["symbol"] == pos["symbol"]), None)
                if g and g.get("status") == "open":
                    if g.get("levels", 1) > pos.get("levels", 1):
                        pos["levels"] = g["levels"]
                        pos["entry_price"] = g["avg_entry"]
                        pos["sl"] = g["initial_entry"] * 0.90
                        pos["tp"] = g["avg_entry"] * 1.02
                        risk_per_unit = pos["entry_price"] - pos["sl"]
                        if risk_per_unit > 0:
                            pos["allocated_capital"] = (pos["risk_amount"] / risk_per_unit) * pos["entry_price"]
                        send_bale(f"🔄 M11-V2 UPDATED GRID | {pos['symbol']} | Levels: {pos['levels']} | New Avg: {pos['entry_price']:.2f}")

    for pos in state["open_positions"][:]:
        current_price = get_current_price(pos["symbol"])
        if current_price == 0: continue
        
        exit_triggered = False
        exit_price = current_price
        
        if pos["strategy"] in ["M9", "VSB"]:
            if current_price <= pos["sl"]: exit_triggered, exit_price = True, pos["sl"]
            elif current_price >= pos["tp"]: exit_triggered, exit_price = True, pos["tp"]
        elif pos["strategy"] == "GRID":
            if current_price >= pos["entry_price"] * 1.02:
                exit_triggered, exit_price = True, current_price
            elif current_price <= pos.get("initial_entry", pos["entry_price"]) * 0.90:
                exit_triggered, exit_price = True, current_price
        elif pos["strategy"] == "LL":
            if time.time() * 1000 - pos["entry_time"] >= (3 * 4 * 3600 * 1000):
                exit_triggered, exit_price = True, current_price
                
        if exit_triggered:
            pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            net_pnl = (pos["allocated_capital"] * pnl_pct) - (pos["allocated_capital"] * 0.002)
            state["capital"] += net_pnl
            
            emoji = "🟢" if net_pnl > 0 else "🔴"
            send_bale(f"{emoji} M11-V2 CLOSED | {pos['strategy']} on {pos['symbol']} | PnL: {net_pnl:.2f} USDT")
            state["open_positions"].remove(pos)
            
    if isinstance(m9_data, dict):
        for t in m9_data.get("trades", []):
            if t.get("status") == "open":
                try_add_position(
                    state, "M9", t["symbol"], t["entry_time"], t["entry_price"], t["sl"], t["tp"],
                    w_m9, 0.005, regime, adx
                )
                    
    if isinstance(ll_data, dict):
        for t in ll_data.get("trades", []):
            if t.get("status") == "open":
                fake_sl = t["entry_price"] * 0.98
                try_add_position(
                    state, "LL", t["symbol"], t["entry_time"], t["entry_price"], fake_sl, 0,
                    w_ll, 0.1 * 0.02, regime, adx
                )
                
    if isinstance(vsb_data, dict):
        for s in vsb_data.get("signals", []):
            if s.get("status") == "open":
                try_add_position(
                    state, "VSB", s["symbol"], s["entry_time"], s["entry_price"], s["sl"], s["tp"],
                    w_vsb, 0.005, regime, adx
                )

    if isinstance(grid_data, dict):
        for g in grid_data.get("signals", []):
            if g.get("status") == "open":
                initial_entry = g.get("initial_entry", g["avg_entry"])
                try_add_position(
                    state, "GRID", g["symbol"], g["entry_time"], g["avg_entry"], initial_entry * 0.90, g["avg_entry"] * 1.02,
                    w_grid, 0.005, regime, adx, initial_entry=initial_entry
                )

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["regime"] = regime
    state["adx"] = adx
    state["total_portfolio_risk"] = round(get_total_portfolio_risk(state), 2)
    
    if save_to_github(STATE_FILE, state, sha):
        total_risk = get_total_portfolio_risk(state)
        rejected_count = len(state["rejected_signals"])
        print(f"M11-V2 updated. Regime: {regime}, Open Pos: {len(state['open_positions'])}, "
              f"Total Risk: {total_risk:.2f} | Rejected (total): {rejected_count}")

if __name__ == "__main__":
    main()
