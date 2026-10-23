import json
import os
import requests
from datetime import datetime, timezone

# ─── Configuration ───
INITIAL_CAPITAL_TOMAN = 1_000_000_000  # ۱ میلیارد تومان
FEE_RATE = 0.002

# ─── Portfolio (11 assets, 3 strategy families) ───
PORTFOLIO = [
    # Family 1: Buy & Hold (uptrend assets)
    ("BTCTMN", "BH", 5.0),
    ("XRPTMN", "BH", 5.0),
    ("BNBTMN", "BH", 5.0),
    ("TRXTMN", "BH", 5.0),
    ("ADATMN", "BH", 5.0),
    # Family 2: Momentum (volatile trend assets)
    ("ETHTMN", "Momentum", 5.0),
    ("SOLTMN", "Momentum", 5.0),
    ("DOGETMN", "Momentum", 5.0),
    # Family 3: Safe Grid (range assets)
    ("DOTTMN", "Grid", 5.0),
    ("AVAXTMN", "Grid", 5.0),
    ("LINKTMN", "Grid", 5.0),
]
# Total: 55% invested, 45% cash reserve

DATA_DIR = "data"
STATE_FILE = "m11_ir_state.json"

BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT = os.environ.get("BALE_CHAT_ID", "")


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


def std_dev(values, period, mean):
    if len(values) < period: return None
    window = values[-period:]
    variance = sum((x - mean) ** 2 for x in window) / period
    return variance ** 0.5


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


def calculate_total_equity(state):
    total = state["capital"]
    for pos in state["positions"]:
        candles = load_candles(pos["symbol"])
        if candles:
            current_price = candles[-1]["c"]
            total += pos["units"] * current_price
    return total


# ─── Signal Checks ───

def check_momentum_signal(candles):
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
    if None in (sma50, rsi_val, atr_val): return None
    if (price > sma50 and 40 < rsi_val < 80 and
        prev_close <= hh20 and price > hh20):
        return "BUY"
    return None


def check_momentum_exit(candles, position):
    if len(candles) < 60: return False
    current = candles[-1]
    price = current["c"]
    window = candles[-50:]
    closes = [c["c"] for c in window]
    sma50 = sma(closes, 50)
    atr_val = atr(window, 14)
    if None in (sma50, atr_val): return False
    if price > position.get("highest", 0):
        position["highest"] = price
        new_stop = price - (2.0 * atr_val)
        if new_stop > position.get("trailing_stop", 0):
            position["trailing_stop"] = new_stop
    if price <= position.get("trailing_stop", 0): return True
    if price < sma50: return True
    return False


def check_grid_signal(candles):
    """Safe Grid entry: price below lower BB and RSI < 35."""
    if len(candles) < 60: return None
    window = candles[-50:]
    closes = [c["c"] for c in window]
    price = candles[-1]["c"]
    mean = sma(closes, 20)
    std = std_dev(closes, 20, mean) if mean else None
    lower_bb = (mean - 2 * std) if (mean and std) else None
    rsi_val = rsi(closes, 14)
    if None in (lower_bb, rsi_val): return None
    if price <= lower_bb and rsi_val < 35:
        return "BUY"
    return None


def check_grid_exit(candles, position):
    """Safe Grid exit conditions."""
    if len(candles) < 60: return (False, None)
    current = candles[-1]
    price = current["c"]
    
    # Hard SL: 10% drop from initial entry
    if price <= position.get("initial_entry", position["entry_price"]) * 0.90:
        return (True, "HARD_SL")
    
    # Take Profit: 2% above average entry
    avg_entry = position.get("avg_entry", position["entry_price"])
    if price >= avg_entry * 1.02:
        return (True, "TAKE_PROFIT")
    
    return (False, None)


def check_grid_avg_levels(candles, position):
    """Check if new grid levels should be added (dollar-cost averaging down)."""
    current = candles[-1]
    price = current["c"]
    initial = position.get("initial_entry", position["entry_price"])
    levels = position.get("levels", 1)
    
    if levels == 1 and price <= initial * 0.97:
        return 2  # Add level 2
    if levels == 2 and price <= initial * 0.94:
        return 3  # Add level 3
    return levels


# ─── Main ───

def main():
    print(f"=== M11-IR Observer ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}) ===\n")
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "capital": INITIAL_CAPITAL_TOMAN,
            "positions": [],
            "history": [],
            "equity_curve": [INITIAL_CAPITAL_TOMAN],
            "last_run": None
        }
    
    if "positions" not in state: state["positions"] = []
    if "history" not in state: state["history"] = []
    if "equity_curve" not in state: state["equity_curve"] = [INITIAL_CAPITAL_TOMAN]
    
    total_equity = calculate_total_equity(state)
    print(f"Starting equity: {total_equity:,.0f} Toman\n")
    
    for symbol, strategy, weight_pct in PORTFOLIO:
        candles = load_candles(symbol)
        if candles is None or len(candles) < 60:
            print(f"  {symbol}: No data")
            continue
        
        current_price = candles[-1]["c"]
        current_time = candles[-1]["t"]
        
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
                if pos["entry_price"] > 0:
                    peak = pos.get("peak", pos["entry_price"])
                    if current_price > peak:
                        pos["peak"] = current_price
                        peak = current_price
                    if current_price <= peak * 0.40:
                        should_close = True
                        reason = "CATASTROPHIC_CRASH"
            
            elif pos["strategy"] == "Grid":
                # Check new levels first
                new_levels = check_grid_avg_levels(candles, pos)
                if new_levels > pos.get("levels", 1):
                    # Add a new level
                    add_amount = pos.get("level_size", pos["size_toman"] / 3)
                    net_inv = add_amount * (1 - FEE_RATE)
                    new_units = net_inv / current_price
                    pos["units"] += new_units
                    pos["size_toman"] += add_amount
                    pos["avg_entry"] = pos["size_toman"] / pos["units"] if pos["units"] > 0 else current_price
                    pos["levels"] = new_levels
                    state["capital"] -= add_amount
                    print(f"  {symbol}: Grid Level {new_levels} added at {current_price:,.0f}")
                    send_bale(f"Grid Level {new_levels}: {symbol} at {current_price:,.0f}")
                
                # Then check exit
                ex, ex_reason = check_grid_exit(candles, pos)
                if ex:
                    should_close = True
                    reason = ex_reason
            
            if should_close:
                exit_value = pos["units"] * current_price * (1 - FEE_RATE)
                pnl = exit_value - pos["size_toman"]
                pnl_pct = (pnl / pos["size_toman"]) * 100
                state["capital"] += exit_value
                
                state["history"].append({
                    "time": current_time,
                    "action": "CLOSE",
                    "symbol": symbol,
                    "strategy": pos["strategy"],
                    "entry_price": pos["entry_price"],
                    "exit_price": current_price,
                    "size_toman": pos["size_toman"],
                    "pnl_toman": round(pnl, 0),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": reason
                })
                state["positions"].remove(pos)
                
                emoji = "🟢" if pnl > 0 else "🔴"
                send_bale(f"{emoji} M11-IR CLOSED\n{symbol} | {pos['strategy']}\nPnL: {pnl:+,.0f} Toman ({pnl_pct:+.2f}%)\nReason: {reason}")
                print(f"  {symbol}: CLOSED | {reason} | PnL={pnl:+,.0f} Toman")
        
        # ─── OPEN NEW POSITION ───
        else:
            signal = None
            if strategy == "Momentum":
                signal = check_momentum_signal(candles)
            elif strategy == "BH":
                signal = "BUY"
            elif strategy == "Grid":
                signal = check_grid_signal(candles)
            
            if signal == "BUY":
                target_size = total_equity * (weight_pct / 100)
                available = state["capital"] * 0.95
                size_toman = min(target_size, available)
                
                if size_toman < 1_000_000:
                    continue
                
                net_inv = size_toman * (1 - FEE_RATE)
                units = net_inv / current_price
                
                new_pos = {
                    "symbol": symbol,
                    "strategy": strategy,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "size_toman": size_toman,
                    "units": units,
                    "peak": current_price if strategy == "BH" else None,
                    "highest": current_price if strategy == "Momentum" else None,
                    "trailing_stop": current_price * 0.90 if strategy == "Momentum" else None,
                    "initial_entry": current_price if strategy == "Grid" else None,
                    "avg_entry": current_price if strategy == "Grid" else None,
                    "levels": 1 if strategy == "Grid" else None,
                    "level_size": size_toman / 3 if strategy == "Grid" else None,
                }
                state["positions"].append(new_pos)
                state["capital"] -= size_toman
                
                state["history"].append({
                    "time": current_time,
                    "action": "OPEN",
                    "symbol": symbol,
                    "strategy": strategy,
                    "price": current_price,
                    "size_toman": round(size_toman, 0)
                })
                
                send_bale(f"🔵 M11-IR OPENED\n{symbol} | {strategy}\nPrice: {current_price:,.0f}\nSize: {size_toman:,.0f} Toman")
                print(f"  {symbol}: OPENED {strategy} at {current_price:,.0f} ({size_toman:,.0f} Toman)")
    
    final_equity = calculate_total_equity(state)
    state["equity_curve"].append(round(final_equity, 0))
    if len(state["equity_curve"]) > 500:
        state["equity_curve"] = state["equity_curve"][-500:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    
    roi = ((final_equity - INITIAL_CAPITAL_TOMAN) / INITIAL_CAPITAL_TOMAN) * 100
    print(f"\n=== Summary ===")
    print(f"  Equity: {final_equity:,.0f} Toman (ROI: {roi:+.2f}%)")
    print(f"  Cash: {state['capital']:,.0f} Toman")
    print(f"  Open positions: {len(state['positions'])}")
    print(f"  State saved to: {STATE_FILE}")


if __name__ == "__main__":
    main()
