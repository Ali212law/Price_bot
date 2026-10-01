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
PRICE_COMPARISON_FILE = "price_comparison.json"

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PERCENT = 0.10
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_PERCENT  # = 0.6%

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

    total_gross = sum(t.get("profit_toman", 0) for t in closed)
    total_net = sum(t.get("profit_net_toman", 0) for t in closed)
    total_costs = total_gross - total_net

    total_wins = sum(t.get("profit_net_toman", 0) for t in wins)
    total_losses = abs(sum(t.get("profit_net_toman", 0) for t in losses))

    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0

    win_rate = len(wins) / len(closed) if closed else 0
    loss_rate = len(losses) / len(closed) if closed else 0

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

    # آمار به تفکیک side
    buys = [t for t in closed if t.get("side") == "buy"]
    sells = [t for t in closed if t.get("side") == "sell"]

    buys_wins = [t for t in buys if t.get("profit_net_toman", 0) > 0]
    sells_wins = [t for t in sells if t.get("profit_net_toman", 0) > 0]

    # آمار به تفکیک سیگنال
    signal_stats = {}
    for t in closed:
        sig = t.get("signal_type", "?")
        if sig not in signal_stats:
            signal_stats[sig] = {"count": 0, "wins": 0, "net_toman": 0}
        signal_stats[sig]["count"] += 1
        signal_stats[sig]["net_toman"] += t.get("profit_net_toman", 0)
        if t.get("profit_net_toman", 0) > 0:
            signal_stats[sig]["wins"] += 1

    return {
        "total": len(trades),
        "closed": len(closed),
        "open": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate * 100,
        "total_gross": total_gross,
        "total_net": total_net,
        "total_costs": total_costs,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "buys_count": len(buys),
        "buys_wins": len(buys_wins),
        "sells_count": len(sells),
        "sells_wins": len(sells_wins),
        "signal_stats": signal_stats,
    }


def analyze_price_comparison():
    data = load_from_github(PRICE_COMPARISON_FILE, silent_404=True)
    if not data:
        return None

    if len(data) < 2:
        return {"count": len(data), "message": "داده کافی نیست"}

    # forward arbitrage (wallex → nobitex)
    fwd_pct = [d.get("diff_executable_pct", 0) for d in data if d.get("diff_executable_pct") is not None]
    fwd_toman = [d.get("diff_executable_toman", 0) for d in data if d.get("diff_executable_toman") is not None]

    # reverse arbitrage (nobitex → wallex)
    rev_pct = [d.get("diff_reverse_pct", 0) for d in data if d.get("diff_reverse_pct") is not None]
    rev_toman = [d.get("diff_reverse_toman", 0) for d in data if d.get("diff_reverse_toman") is not None]

    if not fwd_pct:
        return {"count": len(data), "message": "داده forward کافی نیست"}

    # forward
    fwd_avg = sum(fwd_toman) / len(fwd_toman)
    fwd_avg_pct = sum(fwd_pct) / len(fwd_pct)
    fwd_min = min(fwd_toman)
    fwd_max = max(fwd_toman)

    fwd_pos = [p for p in fwd_pct if p > TOTAL_COST_PERCENT]  # مفید
    fwd_neg = [p for p in fwd_pct if p < -TOTAL_COST_PERCENT]

    # reverse
    if rev_pct:
        rev_avg = sum(rev_toman) / len(rev_toman)
        rev_avg_pct = sum(rev_pct) / len(rev_pct)
        rev_min = min(rev_toman)
        rev_max = max(rev_toman)
        rev_pos = [p for p in rev_pct if p > TOTAL_COST_PERCENT]
        rev_neg = [p for p in rev_pct if p < -TOTAL_COST_PERCENT]
    else:
        rev_avg = 0
        rev_avg_pct = 0
        rev_min = 0
        rev_max = 0
        rev_pos = []
        rev_neg = []

    return {
        "count": len(data),
        # forward
        "fwd_avg_toman": fwd_avg,
        "fwd_avg_pct": fwd_avg_pct,
        "fwd_min_toman": fwd_min,
        "fwd_max_toman": fwd_max,
        "fwd_useful_count": len(fwd_pos),
        "fwd_loss_count": len(fwd_neg),
        "fwd_useful_avg_pct": sum(fwd_pos) / len(fwd_pos) if fwd_pos else 0,
        # reverse
        "rev_avg_toman": rev_avg,
        "rev_avg_pct": rev_avg_pct,
        "rev_min_toman": rev_min,
        "rev_max_toman": rev_max,
        "rev_useful_count": len(rev_pos),
        "rev_loss_count": len(rev_neg),
        "rev_useful_avg_pct": sum(rev_pos) / len(rev_pos) if rev_pos else 0,
    }


def main():
    print("=== ANALYZE 3 ===")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"TOTAL_COST_PERCENT: {TOTAL_COST_PERCENT}%")

    trades = load_from_github(PAPER_TRADES_FILE)
    if not trades:
        print("NO TRADES")
        send_message("📊 آمار Paper Trading\n\n❌ فایلی وجود نداره.")
        return

    stats = calculate_stats(trades)
    print(f"STATS: {stats}")

    if stats.get("closed", 0) > 0:
        net_emoji = "🟢" if stats["total_net"] > 0 else "🔴"

        signal_lines = ""
        for sig, s in stats.get("signal_stats", {}).items():
            wr = (s["wins"] / s["count"] * 100) if s["count"] > 0 else 0
            signal_lines += f"\n  {sig}: {s['count']} | برد {s['wins']} | {wr:.0f}% | {_fmt(s['net_toman'])}"

        msg = f"""📊 آمار Paper Trading

📈 کل: {stats['total']}
✅ بسته: {stats['closed']}
⏳ باز: {stats['open']}

🟢 برنده: {stats['wins']}
🔴 بازنده: {stats['losses']}
📊 Win Rate: {stats['win_rate']:.1f}%

💰 سود/ضرر خام: {_fmt(stats['total_gross'])}
📉 هزینه‌ها: {_fmt(stats['total_costs'])}
{net_emoji} سود/ضرر خالص: {_fmt(stats['total_net'])}

📈 میانگین برد: {_fmt(stats['avg_win'])}
📉 میانگین باخت: {_fmt(stats['avg_loss'])}
🎯 Expectancy: {_fmt(stats['expectancy'])}
📊 Profit Factor: {stats['profit_factor']:.2f}

📊 BUY: {stats['buys_count']} ({stats['buys_wins']} برد)
📊 SELL: {stats['sells_count']} ({stats['sells_wins']} برد)

📋 به تفکیک سیگنال:{signal_lines}"""
        send_message(msg)
    else:
        msg = f"""📊 آمار Paper Trading

📈 کل: {stats['total']}
⏳ باز: {stats['open']}

ℹ️ هنوز معامله‌ای بسته نشده."""
        send_message(msg)

    # تحلیل آربیتراژ دوطرفه
    comp = analyze_price_comparison()
    if comp and "fwd_avg_toman" in comp:
        print(f"COMPARISON: {comp}")

        comp_msg = f"""📊 تحلیل آربیتراژ دوطرفه
(والکس ↔ نوبیتکس)

📅 نمونه: {comp['count']}

━━━━━━━━━━━━━━━━━━━━
🔄 Forward (والکس → نوبیتکس)
━━━━━━━━━━━━━━━━━━━━
(بخر از والکس، بفروش در نوبیتکس)

📈 میانگین: {comp['fwd_avg_pct']:+.3f}%
📊 محدوده: {comp['fwd_min_toman']:+,.0f} تا {comp['fwd_max_toman']:+,.0f}

✅ فرصت مفید (> {TOTAL_COST_PERCENT}%): {comp['fwd_useful_count']}
❌ فرصت منفی: {comp['fwd_loss_count']}
📈 میانگین فرصت‌های مفید: {comp['fwd_useful_avg_pct']:+.3f}%

━━━━━━━━━━━━━━━━━━━━
🔄 Reverse (نوبیتکس → والکس)
━━━━━━━━━━━━━━━━━━━━
(بخر از نوبیتکس، بفروش در والکس)

📈 میانگین: {comp['rev_avg_pct']:+.3f}%
📊 محدوده: {comp['rev_min_toman']:+,.0f} تا {comp['rev_max_toman']:+,.0f}

✅ فرصت مفید (> {TOTAL_COST_PERCENT}%): {comp['rev_useful_count']}
❌ فرصت منفی: {comp['rev_loss_count']}
📈 میانگین فرصت‌های مفید: {comp['rev_useful_avg_pct']:+.3f}%

━━━━━━━━━━━━━━━━━━━━
💰 هزینه معامله: {TOTAL_COST_PERCENT}%

🎯 نتیجه:
- Forward: {'✅ مفید' if comp['fwd_useful_count'] > comp['count'] / 2 else '❌ مفید نیست'}
- Reverse: {'✅ مفید' if comp['rev_useful_count'] > comp['count'] / 2 else '❌ مفید نیست'}"""
        send_message(comp_msg)


if __name__ == "__main__":
    main()
