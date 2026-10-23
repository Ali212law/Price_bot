import requests
from config import BALE_BOT_TOKEN, BALE_CHAT_ID

def send_bale(message, level="INFO"):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        print(f"[BALE] Skipped: {message[:100]}")
        return False
    emoji_map = {
        "INFO": "INFO",
        "SUCCESS": "OK",
        "WARNING": "WARN",
        "ERROR": "ERR",
        "HALT": "HALT",
        "TRADE": "TRADE"
    }
    prefix = emoji_map.get(level, "INFO")
    full_message = f"[{prefix}] {message}"
    try:
        url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": BALE_CHAT_ID,
            "text": full_message
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[BALE] Failed: {e}")
        return False

def notify(message, level="INFO"):
    return send_bale(message, level)

def notify_trade_opened(symbol, side, size_usd, entry_price):
    msg = f"TRADE OPEN | {symbol} | {side} | Size: ${size_usd} | Entry: {entry_price}"
    notify(msg, level="TRADE")

def notify_trade_closed(symbol, pnl_usd, pnl_pct, reason):
    msg = f"TRADE CLOSED | {symbol} | PnL: ${pnl_usd} ({pnl_pct}%) | Reason: {reason}"
    notify(msg, level="SUCCESS" if float(pnl_usd) > 0 else "ERROR")

def notify_transfer_success(tx_hash, amount_usd, symbol):
    msg = f"TRANSFER OK | ${amount_usd} | {symbol} | Tx: {tx_hash[:20]}..."
    notify(msg, level="SUCCESS")

def notify_transfer_failed(reason, details=""):
    msg = f"TRANSFER FAILED | {reason} | {details}"
    notify(msg, level="ERROR")

def notify_halt(reason, details=""):
    msg = f"HALT TRIGGERED | Reason: {reason} | {details} | All trading stopped. Remove HALT_FILE manually to resume."
    notify(msg, level="HALT")

def notify_regime_change(old_regime, new_regime, adx):
    msg = f"REGIME CHANGE | {old_regime} -> {new_regime} | ADX: {adx}"
    notify(msg, level="INFO")
