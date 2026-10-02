import requests
import json
import os
import base64
import time
from datetime import datetime
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"

PAPER_TRADES_FILE = "paper_trades.json"
SHADOW_TRADES_FILE = "shadow_trades.json"
LIVE_TRADES_FILE = "trades_history.json"

TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "False").strip().lower() == "true"

STOP_LOSS_PERCENT = 1.5
TAKE_PROFIT_PERCENT = 3.0

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP  # 0.6%

WALLEX_API_URL = "https://api.wallex.ir"
WALLEX_SYMBOL = "BTCTMN"

bot = Client(BALE_TOKEN)


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def request_with_retry(url, headers=None, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries}: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def put_with_retry(url, headers, json_data, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            r = requests.put(url, headers=headers, json=json_data, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
        except Exception as e:
            print(f"PUT RETRY: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def load_from_github(filename, silent_404=False):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = request_with_retry(url, headers=headers)
        if r and r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        return None, None
    except Exception as e:
        print(f"LOAD ERROR ({filename}): {e}")
        return None, None


def save_to_github(filename, data, sha=None):
    try:
        if not sha:
            _, sha = load_from_github(filename, silent_404=True)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha:
            payload["sha"] = sha
        r = put_with_retry(url, headers, payload)
        if r and r.status_code in [200, 201]:
            print(f"SAVED: {filename}")
            return True
        return False
    except Exception as e:
        print(f"SAVE ERROR ({filename}): {e}")
        return False


def send_message(text):
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": text}
        r = requests.post(url, data=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None


def get_wallex_prices():
    try:
        url = f"{WALLEX_API_URL}/v1/markets"
        r = request_with_retry(url, max_retries=3, timeout=15)
        if not r or r.status_code != 200:
            return None
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        btc = symbols.get(WALLEX_SYMBOL, {})
        stats = btc.get("stats", {})
        if not stats:
            return None
        return {
            "last": float(stats.get("lastPrice", 0)),
            "bid": float(stats.get("bidPrice", 0)),
            "ask": float(stats.get("askPrice", 0)),
        }
    except Exception as e:
        print(f"WALLEX ERROR: {e}")
        return None


def calc_exit(side, entry_price, prices):
    side_low = side.lower()
    if side_low == "buy":
        exit_price = prices["bid"]
        change_pct = ((exit_price - entry_price) / entry_price) * 100
    else:
        exit_price = prices["ask"]
        change_pct = ((entry_price - exit_price) / entry_price) * 100
    return exit_price, change_pct


def calc_pnl(change_pct, amount_toman):
    """PnL خام و خالص"""
    gross_pnl = (change_pct / 100) * amount_toman
    net_pct = change_pct - TOTAL_COST_PERCENT
    net_pnl = (net_pct / 100) * amount_toman
    return round(gross_pnl, 0), round(net_pnl, 0), round(net_pct, 4)


def process_trades(trades, label, prices, now, notify=False, decision_path=None):
    """
    پردازش لیست معاملات (Paper یا Shadow)
    Idempotency: اگه status != open، دوباره بسته نمی‌شه
    """
    changed = False
    if not trades:
        return changed

    open_trades = [t for t in trades if t.get("status") == "open"]
    print(f"  {label} OPEN: {len(open_trades)}")

    for t in trades:
        if t.get("status") != "open":
            continue

        entry = t["entry_price"]
        side = t.get("side", "").lower()
        amount = t.get("amount_toman", 50000)

        exit_price, change_pct = calc_exit(side, entry, prices)

        if change_pct <= -STOP_LOSS_PERCENT:
            action = "stop_loss"
        elif change_pct >= TAKE_PROFIT_PERCENT:
            action = "take_profit"
        else:
            action = None

        if action:
            gross_pnl, net_pnl, net_pct = calc_pnl(change_pct, amount)

            # ثبت تمام فیلدهای لازم
            t["status"] = "closed"
            t["exit_price"] = exit_price
            t["exit_price_toman"] = exit_price
            t["exit_price_irr"] = exit_price * 10
            t["exit_time"] = now.isoformat()
            t["exit_reason"] = action
            t["profit_pct"] = round(change_pct, 4)
            t["profit_toman"] = gross_pnl
            t["gross_pnl"] = gross_pnl
            t["net_pnl"] = net_pnl
            t["profit_net_toman"] = net_pnl
            t["profit_net_pct"] = net_pct
            t["fees_percent"] = TOTAL_COST_PERCENT
            t["fees_toman"] = round(gross_pnl - net_pnl, 0)

            # entry_time (اگه نبود)
            if "entry_time" not in t:
                t["entry_time"] = t.get("time") or t.get("date", "") + "T00:00:00"

            # decision_path
            if "decision_path" not in t:
                if t.get("is_shadow"):
                    st = t.get("shadow_type", "shadow")
                    t["decision_path"] = f"shadow_{st}"
                else:
                    t["decision_path"] = "paper_executed"

            changed = True

            print(f"  {label} {action.upper()}: gross={change_pct:+.2f}% | net={net_pct:+.2f}% | toman_net={net_pnl:+,.0f}")

            if notify:
                emoji = "🟢" if change_pct > 0 else "🔴"
                action_fa = "حد سود" if action == "take_profit" else "حد ضرر"

                shadow_tag = ""
                if t.get("is_shadow"):
                    shadow_type = t.get("shadow_type", "?")
                    if shadow_type == "veto":
                        shadow_tag = "\n👻 Shadow (VETO شده)"
                    elif shadow_type == "top_only":
                        shadow_tag = "\n👻 Shadow (TOP فقط)"
                    else:
                        shadow_tag = f"\n👻 Shadow ({shadow_type})"

                msg = (
                    f"{emoji} {label} بسته شد ({action_fa}){shadow_tag}\n\n"
                    f"📈 سیگنال: {t.get('signal_type', '?')}\n"
                    f"💵 ورود: {_fmt(entry)}\n"
                    f"💵 خروج: {_fmt(exit_price)}\n"
                    f"📊 تغییر خام: {change_pct:+.2f}%\n"
                    f"📉 هزینه: -{TOTAL_COST_PERCENT}%\n"
                    f"✅ خالص: {_fmt(net_pnl)} ({net_pct:+.2f}%)\n"
                    f"💰 حجم: {_fmt(amount)}"
                )
                send_message(msg)

    return changed


def check_paper_trades(prices, now):
    print("\n=== CHECK PAPER TRADES ===")
    trades, sha = load_from_github(PAPER_TRADES_FILE)
    if not trades:
        print("  NO PAPER TRADES FILE")
        return

    if process_trades(trades, "Paper", prices, now, notify=True):
        save_to_github(PAPER_TRADES_FILE, trades)
        print("  PAPER UPDATED")
    else:
        print("  NO CHANGES")


def check_shadow_trades(prices, now):
    print("\n=== CHECK SHADOW TRADES ===")
    trades, sha = load_from_github(SHADOW_TRADES_FILE, silent_404=True)
    if not trades:
        print("  NO SHADOW TRADES FILE")
        return

    if process_trades(trades, "Shadow", prices, now, notify=True):
        save_to_github(SHADOW_TRADES_FILE, trades)
        print("  SHADOW UPDATED")
    else:
        print("  NO CHANGES")


def check_live_trades(prices, now):
    print("\n=== CHECK LIVE TRADES ===")
    trades, sha = load_from_github(LIVE_TRADES_FILE, silent_404=True)
    if not trades:
        print("  NO LIVE TRADES")
        return
    print("  LIVE NOT IMPLEMENTED YET")


def main():
    print("=== MONITOR 9 ===")
    now = datetime.now()

    prices = get_wallex_prices()
    if not prices:
        print("CANNOT GET PRICES - EXIT")
        return
    print(f"WALLEX: bid={prices['bid']:,.0f} | ask={prices['ask']:,.0f} | last={prices['last']:,.0f}")

    check_paper_trades(prices, now)
    check_shadow_trades(prices, now)
    check_live_trades(prices, now)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
