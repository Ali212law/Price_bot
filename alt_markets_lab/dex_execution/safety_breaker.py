import json
import os
from datetime import datetime, timezone
from decimal import Decimal

from config import (
    HALT_FILE, MAX_TRADE_SIZE_USD, MAX_DAILY_TRADES,
    MAX_DAILY_VOLUME_USD, MIN_WALLET_BALANCE_USD, STATE_FILE
)
from notifier import notify_halt, send_bale


def is_halted():
    return os.path.exists(HALT_FILE)


def trigger_halt(reason, details=""):
    """Trigger HALT mode - writes file, notifies, stops all activity."""
    halt_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "details": str(details)
    }
    with open(HALT_FILE, "w") as f:
        json.dump(halt_data, f, indent=2)
    
    notify_halt(reason, details)
    print(f"🚨 HALT TRIGGERED: {reason}")
    return halt_data


def clear_halt():
    """Manual function to clear HALT (for human use only)."""
    if os.path.exists(HALT_FILE):
        os.remove(HALT_FILE)
        send_bale("✅ HALT برداشته شد - ربات‌ها از سر گرفته می‌شوند.", level="SUCCESS")
        return True
    return False


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "daily_trades": 0,
        "daily_volume_usd": "0",
        "open_positions": [],
        "last_run": None,
        "halt_history": []
    }


def save_state(state):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def reset_daily_if_needed(state):
    today = datetime.now(timezone.utc).date().isoformat()
    if state.get("date") != today:
        state["date"] = today
        state["daily_trades"] = 0
        state["daily_volume_usd"] = "0"
    return state


def check_all_safety(trade_size_usd, wallet_balance_usd):
    """Comprehensive safety check before any trade."""
    # 1. HALT active?
    if is_halted():
        return False, "HALT_ACTIVE"
    
    # 2. Trade size limit
    if Decimal(str(trade_size_usd)) > MAX_TRADE_SIZE_USD:
        return False, f"TRADE_SIZE_EXCEEDED ({trade_size_usd} > {MAX_TRADE_SIZE_USD})"
    
    # 3. Wallet balance
    if Decimal(str(wallet_balance_usd)) < MIN_WALLET_BALANCE_USD:
        return False, f"WALLET_BALANCE_LOW ({wallet_balance_usd} < {MIN_WALLET_BALANCE_USD})"
    
    # 4. Daily counters
    state = load_state()
    state = reset_daily_if_needed(state)
    
    if state["daily_trades"] >= MAX_DAILY_TRADES:
        return False, f"DAILY_TRADE_LIMIT_REACHED ({state['daily_trades']}/{MAX_DAILY_TRADES})"
    
    new_daily_volume = Decimal(state["daily_volume_usd"]) + Decimal(str(trade_size_usd))
    if new_daily_volume > MAX_DAILY_VOLUME_USD:
        return False, f"DAILY_VOLUME_LIMIT_REACHED ({new_daily_volume} > {MAX_DAILY_VOLUME_USD})"
    
    return True, "OK"


def record_trade(trade_size_usd, position_data=None):
    state = load_state()
    state = reset_daily_if_needed(state)
    state["daily_trades"] += 1
    state["daily_volume_usd"] = str(
        Decimal(state["daily_volume_usd"]) + Decimal(str(trade_size_usd))
    )
    if position_data:
        state["open_positions"].append(position_data)
    save_state(state)


def record_closed_position(position_id, pnl_usd):
    state = load_state()
    state["open_positions"] = [p for p in state["open_positions"] if p.get("id") != position_id]
    save_state(state)
