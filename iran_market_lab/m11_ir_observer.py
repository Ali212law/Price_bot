import json
import os
import requests
from datetime import datetime, timezone

# ─── Configuration ───
INITIAL_CAPITAL = 10000.0
FEE_RATE = 0.002  # 0.2% per side (buy + sell)

# Strategy assignment per asset
# Format: (asset_symbol, strategy_name, weight_pct)
PORTFOLIO = [
    ("ETHTMN", "Momentum", 16.67),
    ("SOLTMN", "Momentum", 16.67),
    ("DOGETMN", "Momentum", 16.67),
    ("BTCTMN", "BH", 16.67),
    ("XRPTMN", "BH", 16.67),
    ("ADATMN", "BH", 16.66),
]

DATA_DIR = "data"
STATE_FILE = "m11_ir_state.json"

# Bale notification
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")


# ─── Helpers ───
def send_bale(msg):
    if not BALE_TOKEN or not BALE_CHAT:
        print(f"[BALE] Skipped: {msg[:80]}")
        return
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": BALE_CHAT, "text": msg}, timeout=10)
    except Exception as e:
        print(f"[BALE] Error: {e}")


def load_candles(symbol):
    path = f"{DATA_DIR}/{symbol}_4h.json"
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def sma(values, period):
    if len(values) < period: return None
    return sum(values[-period:]) / period


def rsi(closes, period=14):
    if len(closes) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + (avg_gain / avg_loss)))


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, prev_c = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs[-period:]) / period


# ─── Strategy Checks (return: "BUY", "SELL", or None) ───

def check_momentum_signal(candles):
    """Momentum: SMA50 + RSI(40-80) + 20-candle breakout."""
    if len(candles) < 60: return None
    window = candles[-50:]
    closes = [c["c"] for c in window]
    current = candles[-1]
    price = current["c"]
    
    sma50 = sma(closes, 50)
    rsi_val = rsi(closes, 14)
    atr_val = atr(window, 14)
    prev_20 = candles[-21:-1]
    if len(prev_20) < 20: return None
    hh20 = max(c["h"] for c in prev_20)
    prev_close = candles[-2]["c"]
    
    if None in (sma50, rsi_val, atr_val):
        return None
    
    # Entry
    if (price > sma50 and 40 < rsi_val < 80 and 
        prev_close <= hh20 and price > hh20):
        return "BUY"
    
    return None


def check_momentum_exit(candles, position):
    """Check if momentum position should be closed."""
    if len(candles) < 60: return False
    
    current = candles[-1]
    price = current["c"]
    window = candles[-50:]
    closes = [c["c"] for c in window]
    
    sma50 = sma(closes, 50)
    atr_val = atr(window, 14)
    
    if None in (sma50, atr_val):
        return False
    
    # Update trailing stop
    if price > position.get("highest", 0):
        position["highest"] = price
        new_stop = price - (2.0 * atr_val)
        if new_stop > position.get("trailing_stop", 0):
            position["trailing_stop"] = new_stop
    
    # Exit conditions
    if price <= position.get("trailing_stop", 0):
        return True
    if price < sma50:
        return True
    
    return False


# ─── Main ───

def main():
    print(f"=== M11-IR Observer ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}) ===\n")
    
    # Load state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "capital": INITIAL_CAPITAL,
            "positions": [],
            "history": [],
            "equity_curve": [INITIAL_CAPITAL],
            "last_run": None
        }
    
    # Ensure all required fields
    if "positions" not in state: state["positions"] = []
    if "history" not in state: state["history"] = []
    if "equity_curve" not in state: state["equity_curve"] = [INITIAL_CAPITAL]
    
    # Process each asset
    for symbol, strategy, weight_pct in PORTFOLIO:
        candles = load_candles(symbol)
        if candles is None or len(candles) < 60:
            print(f"  {symbol}: No data")
            continue
        
        current_price = candles[-1]["c"]
        current_time = candles[-1]["t"]
        
        # Find existing position
        pos = None
        for p in state["positions"]:
            if p["symbol"] == symbol:
                pos = p
                break
        
        # ─── MANAGE EXISTING POSITION ───
        if pos:
            should_close = False
            reason = None
            
            if pos["strategy"] == "Momentum":
                if check_momentum_exit(candles, pos):
                    should_close = True
                    reason = "MOMENTUM_EXIT"
            elif pos["strategy"] == "BH":
                # B&H: only close if 60% crash from peak (catastrophic protection)
                if pos["entry_price"] > 0:
                    peak = pos.get("peak", pos["entry_price"])
                    if current_price > peak:
                        pos["peak"] = current_price
                        peak = current_price
                    if current_price <= peak * 0.40:
                        should_close = True
                        reason = "CATASTROPHIC_CRASH"
            
            if should_close:
                exit_value = pos["size_usd"] * (current_price / pos["entry_price"])
                exit_value *= (1 - FEE_RATE)  # Sell fee
                pnl_usd = exit_value - pos["size_usd"]
                pnl_pct = (pnl_usd / pos["size_usd"]) * 100
                
                state["capital"] += exit_value
                
                history_entry = {
                    "time": current_time,
                    "action": "CLOSE",
                    "symbol": symbol,
                    "strategy": pos["strategy"],
                    "entry_price": pos["entry_price"],
                    "exit_price": current_price,
                    "size_usd": pos["size_usd"],
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": reason
                }
                state["history"].append(history_entry)
                state["positions"].remove(pos)
                
                emoji = "🟢" if pnl_usd > 0 else "🔴"
                send_bale(f"{emoji} M11-IR CLOSED\n{symbol} | {pos['strategy']}\nPnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)\nReason: {reason}")
                print(f"  {symbol}: CLOSED | {reason} | PnL=${pnl_usd:+.2f}")
        
        # ─── OPEN NEW POSITION ───
        else:
            signal = None
            if strategy == "Momentum":
                signal = check_momentum_signal(candles)
            elif strategy == "BH":
                # B&H: always open if no position (buy and hold)
                signal = "BUY"
            
            if signal == "BUY":
                size_usd = state["capital"] * (weight_pct / 100)
                if size_usd < 10:  # Minimum $10
                    continue
                
                # Apply fee
                net_investment = size_usd * (1 - FEE_RATE)
                units = net_investment / current_price
                
                new_pos = {
                    "symbol": symbol,
                    "strategy": strategy,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "size_usd": size_usd,
                    "units": units,
                    "peak": current_price if strategy == "BH" else None,
                    "highest": current_price if strategy == "Momentum" else None,
                    "trailing_stop": current_price * 0.90 if strategy == "Momentum" else None
                }
                state["positions"].append(new_pos)
                state["capital"] -= size_usd
                
                history_entry = {
                    "time": current_time,
                    "action": "OPEN",
                    "symbol": symbol,
                    "strategy": strategy,
                    "price": current_price,
                    "size_usd": round(size_usd, 2)
                }
                state["history"].append(history_entry)
                
                send_bale(f"🔵 M11-IR OPENED\n{symbol} | {strategy}\nPrice: {current_price:,.0f}\nSize: ${size_usd:.2f}")
                print(f"  {symbol}: OPENED {strategy} at {current_price:,.0f} (${size_usd:.2f})")
    
    # ─── CALCULATE EQUITY ───
    total_equity = state["capital"]
    for pos in state["positions"]:
        candles = load_candles(pos["symbol"])
        if candles:
            current_price = candles[-1]["c"]
            pos_value = pos["units"] * current_price
            total_equity += pos_value
    
    state["equity_curve"].append(round(total_equity, 2))
    if len(state["equity_curve"]) > 500:
        state["equity_curve"] = state["equity_curve"][-500:]
    
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    
    # Save state
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    
    # Summary
    roi = ((total_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    print(f"\n=== Summary ===")
    print(f"  Equity: ${total_equity:.2f} (ROI: {roi:+.2f}%)")
    print(f"  Cash: ${state['capital']:.2f}")
    print(f"  Open positions: {len(state['positions'])}")
    print(f"  State saved to: {STATE_FILE}")


if __name__ == "__main__":
    main()
