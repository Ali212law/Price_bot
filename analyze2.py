import requests
import json
import os
import base64
import time
from datetime import datetime, timedelta
from pyrobale import Client

BALE_TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_REPO = "Ali212law/Price_bot"

PAPER_TRADES_FILE = "paper_trades.json"
PRICE_COMPARISON_FILE = "price_comparison.json"

FEE_PERCENT = 0.25
SPREAD_PERCENT = 0.10
SLIPPAGE_PERCENT = 0.10
TOTAL_COST_PERCENT = FEE_PERCENT * 2 + SPREAD_PERCENT + SLIPPAGE_PERCENT

bot = Client(BALE_TOKEN)


def _fmt(v):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def request_with_retry(url, headers=None, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
            print(f"RETRY {attempt+1}/{max_retries} - Status: {r.status_code}")
        except Exception as e:
            print(f"RETRY {attempt+1}/{max_retries} - Error: {e}")
        if attempt < max_retries - 1:
            time.sleep(3 ** attempt)
    return None


def load_from_github(filename, silent_404=False):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = request_with_retry(url, headers=headers)
        if r and r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content)
        if r and r.status_code == 404 and not silent_404:
            print(f"FILE NOT FOUND: {filename}")
        return None
    except Exception as e:
        print(f"LOAD ERROR ({filename}): {e}")
        return None


def send_message(text):
    try:
        url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": text}
        r = requests.post(url, data=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None


def calculate_stats(trades):
    if not trades:
        return None

    closed = [t for t in trades if t.get("status") == "closed"]
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not closed:
        return {
            "total": len(trades),
            "closed": 0,
            "open": len(open_trades),
            "message": "هنوز معامله‌ای بسته نشده",
        }

    wins = [t for t in closed if t.get("profit_net_toman", 0) > 0]
    losses = [t for t in closed if t.get("profit_net_toman", 0) < 0]

    total_profit_gross = sum(t.get("profit_toman", 0) for t in closed)
    total_profit_net = sum(t.get("profit_net_toman", 0) for t in closed)

    total_wins = sum(t.get("profit_net_toman", 0) for t in wins)
    total_losses = abs(sum(t.get("profit_net_toman", 0) for t in losses))

    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0

    win_rate = len(wins) / len(closed) if closed else 0
    loss_rate = len(losses) / len(closed) if closed else 0

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

    return {
        "total": len(trades),
        "closed": len(closed),
        "open": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate * 100,
        "total_profit_gross": total_profit_gross,
        "total_profit_net": total_profit_net,
        "total_costs": total_profit_gross - total_profit_net,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
    }


def analyze_price_comparison():
    data = load_from_github(PRICE_COMPARISON_FILE, silent_404=True)
    if not data:
        return None

    if len(data) < 2:
        return {"count": len(data), "message": "داده کافی نیست"}

    diffs_exec = [d.get("diff_executable_toman", 0) for d in data]
    diffs_exec_pct = [d.get("diff_executable_pct", 0) for d in data]

    diffs_exec = [d for d in diffs_exec if d != 0]
    diffs_exec_pct = [d for d in diffs_exec_pct if d != 0]

    if not diffs_exec:
        return {"count": len(data), "message": "داده کافی نیست"}

    avg_diff = sum(diffs_exec) / len(diffs_exec)
    avg_diff_pct = sum(diffs_exec_pct) / len(diffs_exec_pct)

    min_diff = min(diffs_exec)
    max_diff = max(diffs_exec)

    positive = [d for d in diffs_exec_pct if d > 0]
    negative = [d for d in diffs_exec_pct if d < 0]

    return {
        "count": len(data),
        "avg_diff_toman": avg_diff,
        "avg_diff_pct": avg_diff_pct,
        "min_diff_toman": min_diff,
        "max_diff_toman": max_diff,
        "positive_count": len(positive),
        "negative_count": len(negative),
        "avg_positive_pct": sum(positive) / len(positive) if positive else 0,
        "avg_negative_pct": sum(negative) / len(negative) if negative else 0,
    }


def main():
    print("=== ANALYZE 2 ===")
    print(f"Time: {datetime.now().isoformat()}")

    trades = load_from_github(PAPER_TRADES_FILE)
    if not trades:
        print("NO TRADES")
        send_message("📊 آمار Paper Trading\n\n❌ فایلی وجود نداره.")
        return

    stats = calculate_stats(trades)
    print(f"STATS: {stats}")

    if stats.get("closed", 0) > 0:
        net_emoji = "🟢" if stats["total_profit_net"] > 0 else "🔴"

        msg = f"""📊 آمار Paper Trading

📈 کل: {stats['total']}
✅ بسته: {stats['closed']}
⏳ باز: {stats['open']}

🟢 برنده: {stats['wins']}
🔴 بازنده: {stats['losses']}
📊 Win Rate: {stats['win_rate']:.1f}%

💰 سود/ضرر خام: {_fmt(stats['total_profit_gross'])}
📉 هزینه‌ها: {_fmt(stats['total_costs'])}
{net_emoji} سود/ضرر خالص: {_fmt(stats['total_profit_net'])}

📈 میانگین برد: {_fmt(stats['avg_win'])}
📉 میانگین باخت: {_fmt(stats['avg_loss'])}
🎯 Expectancy: {_fmt(stats['expectancy'])}
📊 Profit Factor: {stats['profit_factor']:.2f}"""
        send_message(msg)
    else:
        msg = f"""📊 آمار Paper Trading

📈 کل: {stats['total']}
⏳ باز: {stats['open']}

ℹ️ هنوز معامله‌ای بسته نشده."""
        send_message(msg)

    comp = analyze_price_comparison()
    if comp and "avg_diff_toman" in comp:
        print(f"COMPARISON: {comp}")

        total_cost = TOTAL_COST_PERCENT
        avg_pos_pct = comp["avg_positive_pct"]

        arb_useful = avg_pos_pct > total_cost

        comp_msg = f"""📊 تحلیل اختلاف قیمت (والکس/نوبیتکس)

📅 تعداد نمونه: {comp['count']}

📈 میانگین اختلاف: {_fmt(comp['avg_diff_toman'])} تومان ({comp['avg_diff_pct']:+.3f}%)
📉 کمترین: {_fmt(comp['min_diff_toman'])}
📈 بیشترین: {_fmt(comp['max_diff_toman'])}

🔵 اختلاف مثبت (نوبیتکس گران‌تر): {comp['positive_count']} بار
🔴 اختلاف منفی (والکس گران‌تر): {comp['negative_count']} بار

📊 میانگین اختلاف مثبت: {comp['avg_positive_pct']:+.3f}%
📊 میانگین اختلاف منفی: {comp['avg_negative_pct']:+.3f}%

💰 هزینه‌های معامله: {total_cost}%
🎯 آربیتراژ {'مفید است ✅' if arb_useful else 'مفید نیست ❌'}"""
        send_message(comp_msg)


if __name__ == "__main__":
    main()
