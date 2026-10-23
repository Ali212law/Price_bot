import os, json, base64, requests, math
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
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")

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
            return json.loads(base64.b64decode(data["content"]).decode("utf-8"))
        return {}
    except: return {}

def calculate_wilson_lower(wins, total, z=1.96):
    if total == 0: return 0
    p = wins / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator

def analyze_strategy(name, trades):
    if not trades:
        return f"🔹 {name}: No trades yet."
        
    closed = [t for t in trades if t.get("status") == "closed"]
    if not closed:
        return f"🔹 {name}: {len(trades)} open positions, no closed trades yet."
        
    total = len(closed)
    wins = sum(1 for t in closed if t.get("pnl", 0) > 0 or t.get("exit_reason") == "TP" or (t.get("exit_price", 0) > t.get("entry_price", 0)))
    net_pnl = sum(t.get("pnl", 0) for t in closed)
    
    win_rate = (wins / total) * 100
    wilson = calculate_wilson_lower(wins, total) * 100
    
    progress = f"({total}/30 to verdict)" if name == "M9" else ""
    
    return (f"🔹 {name}: n={total} {progress} | WinRate={win_rate:.1f}% | Wilson={wilson:.1f}%\n"
            f"   Total PnL: {net_pnl:.2f}")

def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = [f"📊 **Daily Project Report** ({now})\n"]
    alerts = []

    # ─── 1. CRYPTO SECTION ───
    report.append("🇺🇸 **Crypto (Global)**")
    
    # M9
    m9_data = load_from_github("paper_m9_trades.json")
    m9_trades = m9_data.get("trades", [])
    report.append(analyze_strategy("M9", m9_trades))
    
    # Lead-Lag
    ll_data = load_from_github("shadow_lead_lag_trades.json")
    ll_trades = ll_data.get("trades", [])
    report.append(analyze_strategy("Lead-Lag", ll_trades))
    
    # VSB
    vsb_data = load_from_github("vsb_signals.json")
    vsb_signals = vsb_data.get("signals", [])
    report.append(analyze_strategy("VSB", vsb_signals))
    
    # M11-V2 Portfolio
    m11_data = load_from_github("m11_v2_portfolio.json")
    if m11_data:
        cap = m11_data.get("capital", 10000.0)
        open_pos = m11_data.get("open_positions", [])
        regime = m11_data.get("regime", "UNKNOWN")
        adx = m11_data.get("adx", 0)
        total_risk = sum(p.get("risk_amount", 0) for p in open_pos)
        roi = ((cap - 10000.0) / 10000.0) * 100
        
        report.append(f"🏦 **M11-V2 Portfolio**")
        report.append(f"   Capital: ${cap:.2f} (ROI: {roi:+.2f}%)")
        report.append(f"   Regime: {regime} (ADX: {adx})")
        report.append(f"   Open Positions: {len(open_pos)} | Total Risk: ${total_risk:.2f}")
        
        if roi < -5:
            alerts.append(f"⚠️ M11-V2 Drawdown Alert: ROI is {roi:.2f}%")
            
        last_run = m11_data.get("last_run", "")
        if last_run:
            last_run_dt = datetime.fromisoformat(last_run)
            if (datetime.now(timezone.utc) - last_run_dt).total_seconds() > 7200:
                alerts.append("⚠️ M11-V2 has not run in the last 2 hours!")

    report.append("")
    
    # ─── 2. IRAN MARKET SECTION ───
    report.append("🇮🇷 **Iran Market**")
    
    ir_data = load_from_github("iran_market_lab/m11_ir_state.json")
    if ir_data:
        ir_cap = ir_data.get("capital", 0)
        ir_positions = ir_data.get("positions", [])
        equity_curve = ir_data.get("equity_curve", [0])
        current_equity = equity_curve[-1] if equity_curve else ir_cap
        
        # Initial capital is 1,000,000,000
        roi = ((current_equity - 1000000000) / 1000000000) * 100
        
        report.append(f"🏦 **M11-IR Portfolio**")
        report.append(f"   Equity: {current_equity:,.0f} Toman (ROI: {roi:+.2f}%)")
        report.append(f"   Cash: {ir_cap:,.0f} Toman")
        report.append(f"   Open Positions: {len(ir_positions)}")
        
        # List positions
        for p in ir_positions:
            report.append(f"   - {p['symbol']} ({p['strategy']})")
            
        if roi < -5:
            alerts.append(f"⚠️ M11-IR Drawdown Alert: ROI is {roi:.2f}%")
            
        last_run = ir_data.get("last_run", "")
        if last_run:
            last_run_dt = datetime.fromisoformat(last_run)
            if (datetime.now(timezone.utc) - last_run_dt).total_seconds() > 7200:
                alerts.append("⚠️ M11-IR has not run in the last 2 hours!")
    else:
        report.append("🔹 M11-IR: State file not found or empty.")

    final_report = "\n".join(report)
    print(final_report)
    
    # Send to Bale
    if alerts:
        final_report += "\n\n🚨 **ALERTS:**\n" + "\n".join(alerts)
        
    send_bale(final_report)

if __name__ == "__main__":
    main()
