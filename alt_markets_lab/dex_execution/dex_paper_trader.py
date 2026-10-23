import json
import os
import time
import requests
from datetime import datetime, timezone
from decimal import Decimal

from config import (
    DRY_RUN, PAIR, MAX_TRADE_SIZE_USD, DEFAULT_SL_PCT, DEFAULT_TP_PCT,
    MAX_POSITIONS, LOG_FILE
)
from notifier import (
    notify_trade_opened, notify_trade_closed, notify
)
from safety_breaker import (
    is_halted, check_all_safety, record_trade,
    record_closed_position, load_state
)

BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"


# ─── Pure Python indicators (no pandas/numpy) ───

def fetch_klines(symbol="BNBUSDT", interval="4h", limit=100):
    """دریافت کندل‌های OHLCV به صورت لیست dict"""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
        if r.status_code != 200:
            print(f"[BINANCE] HTTP {r.status_code}: {r.text[:200]}")
            return None
        raw = r.json()
        candles = []
        for k in raw:
            candles.append({
                "timestamp": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            })
        return candles
    except Exception as e:
        print(f"[BINANCE] Error: {e}")
        return None


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def std_dev(values, period, mean):
    if len(values) < period:
        return None
    window = values[-period:]
    variance = sum((x - mean) ** 2 for x in window) / period
    return variance ** 0.5


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs[-period:]) / period


def calculate_indicators(candles):
    closes = [c["close"] for c in candles]
    sma20 = sma(closes, 20)
    std20 = std_dev(closes, 20, sma20) if sma20 else None
    lower_bb = (sma20 - 2 * std20) if (sma20 and std20) else None
    rsi_val = rsi(closes, 14)
    atr_val = atr(candles, 14)
    return {
        "sma20": sma20,
        "lower_bb": lower_bb,
        "rsi": rsi_val,
        "atr": atr_val,
        "current_price": closes[-1] if closes else None
    }


def check_exit_conditions(position, current_price):
    entry_price = Decimal(str(position['entry_price']))
    current_price = Decimal(str(current_price))
    pnl_pct = float((current_price - entry_price) / entry_price * 100)
    if pnl_pct >= DEFAULT_TP_PCT:
        return True, "TAKE_PROFIT", pnl_pct
    if pnl_pct <= -DEFAULT_SL_PCT:
        return True, "STOP_LOSS", pnl_pct
    return False, None, pnl_pct


def append_log(entry):
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append(entry)
    if len(logs) > 500:
        logs = logs[-500:]
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)


def main():
    print(f"=== DEX Paper Trader (DRY_RUN={DRY_RUN}) ===")

    if is_halted():
        print("HALT active - skipping all operations.")
        return

    print(f"Fetching {PAIR} klines...")
    candles = fetch_klines(symbol="BNBUSDT", interval="4h", limit=100)
    if not candles or len(candles) < 30:
        print("Insufficient data. Exiting.")
        return

    indicators = calculate_indicators(candles)
    current_price = indicators["current_price"]
    lower_bb = indicators["lower_bb"]
    rsi_val = indicators["rsi"]
    atr_val = indicators["atr"]

    if None in (current_price, lower_bb, rsi_val, atr_val):
        print("Not enough data for indicators. Exiting.")
        return

    print(f"Price: {current_price:.2f} | Lower BB: {lower_bb:.2f} | RSI: {rsi_val:.2f} | ATR: {atr_val:.2f}")

    state = load_state()

    for position in state['open_positions'][:]:
        should_exit, reason, pnl_pct = check_exit_conditions(position, current_price)
        if should_exit:
            entry = Decimal(str(position['entry_price']))
            current = Decimal(str(current_price))
            pnl_usd = float((current - entry) / entry * position['size_usd'])
            print(f"Closing {position['id']} | {reason} | PnL: {pnl_pct:.2f}% (${pnl_usd:.2f})")
            notify_trade_closed(position['symbol'], pnl_usd, pnl_pct, reason)
            record_closed_position(position['id'], pnl_usd)
            append_log({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "CLOSE",
                "position_id": position['id'],
                "symbol": position['symbol'],
                "entry_price": position['entry_price'],
                "exit_price": current_price,
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd,
                "reason": reason
            })

    if len(state['open_positions']) < MAX_POSITIONS:
        if current_price <= lower_bb and rsi_val < 35:
            trade_size = float(MAX_TRADE_SIZE_USD)
            wallet_balance = 1000.0
            allowed, reason = check_all_safety(trade_size, wallet_balance)
            if allowed:
                sl_price = current_price * (1 - DEFAULT_SL_PCT / 100)
                tp_price = current_price * (1 + DEFAULT_TP_PCT / 100)
                position = {
                    "id": f"pos_{int(time.time())}",
                    "symbol": PAIR,
                    "side": "LONG",
                    "entry_price": current_price,
                    "size_usd": trade_size,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "opened_at": datetime.now(timezone.utc).isoformat()
                }
                print(f"Opening LONG at {current_price:.2f} | Size: ${trade_size} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")
                notify_trade_opened(PAIR, "LONG", trade_size, current_price)
                record_trade(trade_size, position)
                append_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "OPEN",
                    "position_id": position['id'],
                    "symbol": PAIR,
                    "side": "LONG",
                    "entry_price": current_price,
                    "size_usd": trade_size,
                    "sl_price": sl_price,
                    "tp_price": tp_price
                })
            else:
                print(f"Signal blocked by safety: {reason}")
        else:
            print("No entry signal (price above lower BB or RSI >= 35).")
    else:
        print(f"Max positions reached ({len(state['open_positions'])}/{MAX_POSITIONS}).")

    print("=== Done ===")


if __name__ == "__main__":
    main()
