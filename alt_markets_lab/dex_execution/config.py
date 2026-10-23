import requests
from config import BALE_BOT_TOKEN, BALE_CHAT_ID

def send_bale(message, level="INFO"):
    """Send notification to Bale messenger."""
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        print(f"[BALE] Skipped (missing credentials): {message[:100]}")
        return False
    
    emoji_map = {
        "INFO": "ℹ️",
        "SUCCESS": "🟢",
        "WARNING": "🟡",
        "ERROR": "🔴",
        "HALT": "🚨",
        "TRADE": "💱"
    }
    emoji = emoji_map.get(level, "ℹ️")
    full_message = f"{emoji} {message}"
    
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
    """Send notification via Bale only (email disabled for now)."""
    return send_bale(message, level)


# ─── Notification Shortcuts ───

def notify_trade_opened(symbol, side, size_usd, entry_price):
    msg = (f"💱 پوزیشن باز شد\n"
           f"جفت: {symbol}\n"
           f"جهت: {side}\n"
           f"حجم: ${size_usd}\n"
           f"قیمت ورود: {entry_price}")
    notify(msg, level="TRADE")


def notify_trade_closed(symbol, pnl_usd, pnl_pct, reason):
    emoji = "🟢" if float(pnl_usd) > 0 else "🔴"
    msg = (f"{emoji} پوزیشن بسته شد\n"
           f"جفت: {symbol}\n"
           f"سود/ضرر: ${pnl_usd}\n"
           f"درصد: {pnl_pct}%\n"
           f"دلیل: {reason}")
    notify(msg, level="SUCCESS" if float(pnl_usd) > 0 else "ERROR")


def notify_transfer_success(tx_hash, amount_usd, symbol):
    msg = (f"🟢 انتقال موفق\n"
           f"مبلغ: ${amount_usd}\n"
           f"دارایی: {symbol}\n"
           f"هش: {tx_hash[:20]}...")
    notify(msg, level="SUCCESS")


def notify_transfer_failed(reason, details=""):
    msg = (f"🔴 انتقال ناموفق!\n"
           f"دلیل: {reason}\n"
           f"جزئیات: {details}")
    notify(msg, level="ERROR")


def notify_halt(reason, details=""):
    msg = (f"🚨 توقف اضطراری فعال شد!\n"
           f"دلیل: {reason}\n"
           f"جزئیات: {details}\n"
           f"⛔️ تمام معاملات متوقف شد.\n"
           f"لطفاً بررسی کنید و فایل HALT_FILE را حذف کنید.")
    notify(msg, level="HALT")


def notify_regime_change(old_regime, new_regime, adx):
    msg = (f"⚖️ تغییر رژیم بازار\n"
           f"از: {old_regime} → به: {new_regime}\n"
           f"ADX: {adx}")
    notify(msg, level="INFO")
