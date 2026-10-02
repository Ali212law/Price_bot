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
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_PERCENT  # 0.6%

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


# ═══════════════════════════════════════════
# آمار Paper Trades
# ═══════════════════════════════════════════

def calculate_stats(trades):
    if not trades:
        return None

    closed = [t for t in trades if t.get("status") == "closed"]
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not closed:
        return {
            "total": len(trades), "closed": 0, "open": len(open_trades),
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
        "total": len(trades), "closed": len(closed), "open": len(open_trades),
        "wins": len(wins), "losses": len(losses), "win_rate": win_rate * 100,
        "total_gross": total_gross, "total_net": total_net, "total_costs": total_costs,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "expectancy": expectancy, "profit_factor": profit_factor,
        "buys_count": len(buys), "buys_wins": len(buys_wins),
        "sells_count": len(sells), "sells_wins": len(sells_wins),
        "signal_stats": signal_stats,
    }


# ═══════════════════════════════════════════
# تحلیل آربیتراژ سه‌گانه
# ═══════════════════════════════════════════

def analyze_arbitrage_pair(data, key_toman, key_pct):
    """تحلیل یه جفت آربیتراژ"""
    tomans = [d.get(key_toman) for d in data if d.get(key_toman) is not None]
    pcts = [d.get(key_pct) for d in data if d.get(key_pct) is not None]

    if not pcts:
        return None

    avg_pct = sum(pcts) / len(pcts)
    avg_toman = sum(tomans) / len(tomans) if tomans else 0

    useful = [p for p in pcts if p > TOTAL_COST_PERCENT]
    loss = [p for p in pcts if p < -TOTAL_COST_PERCENT]

    return {
        "count": len(pcts),
        "avg_pct": avg_pct,
        "avg_toman": avg_toman,
        "min_pct": min(pcts),
        "max_pct": max(pcts),
        "useful_count": len(useful),
        "useful_pct": (len(useful) / len(pcts) * 100) if pcts else 0,
        "avg_useful": sum(useful) / len(useful) if useful else 0,
        "loss_count": len(loss),
        "best_pct": max(pcts) if pcts else 0,
    }


def analyze_all_pairs():
    data = load_from_github(PRICE_COMPARISON_FILE, silent_404=True)
    if not data or len(data) < 2:
        return None

    pairs = {
        # والکس ↔ نوبیتکس
        "والکس → نوبیتکس": ("wallex_to_nobitex", "wallex_to_nobitex_pct"),
        "نوبیتکس → والکس": ("nobitex_to_wallex", "nobitex_to_wallex_pct"),
        # والکس ↔ آبان
        "والکس → آبان": ("wallex_to_aban", "wallex_to_aban_pct"),
        "آبان → والکس": ("aban_to_wallex", "aban_to_wallex_pct"),
        # آبان ↔ نوبیتکس
        "آبان → نوبیتکس": ("aban_to_nobitex", "aban_to_nobitex_pct"),
        "نوبیتکس → آبان": ("nobitex_to_aban", "nobitex_to_aban_pct"),
    }

    results = {"count": len(data)}
    for name, (key_toman, key_pct) in pairs.items():
        r = analyze_arbitrage_pair(data, key_toman, key_pct)
        results[name] = r

    # اسپرد صرافی‌ها
    if data:
        wallex_spreads = [d.get("wallex_spread_pct", 0) for d in data if d.get("wallex_spread_pct") is not None]
        results["wallex_avg_spread"] = sum(wallex_spreads) / len(wallex_spreads) if wallex_spreads else 0

        aban_spreads = [d.get("aban_spread_pct", 0) for d in data if d.get("aban_spread_pct") is not None]
        results["aban_avg_spread"] = sum(aban_spreads) / len(aban_spreads) if aban_spreads else 0

    return results


def format_pair_report(name, r):
    if not r:
        return f"\n{name}: ❌ داده کافی نیست"
    return (
        f"\n{name}:\n"
        f"  میانگین: {r['avg_pct']:+.3f}%\n"
        f"  بهترین: {r['best_pct']:+.3f}%\n"
        f"  محدوده: {r['min_pct']:+.3f}% تا {r['max_pct']:+.3f}%\n"
        f"  ✅ فرصت مفید (>{TOTAL_COST_PERCENT}%): {r['useful_count']} ({r['useful_pct']:.1f}%)\n"
        f"  📈 میانگین فرصت‌های مفید: {r['avg_useful']:+.3f}%"
    )


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    print("=== ANALYZE 4 (سه‌گانه) ===")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"TOTAL_COST_PERCENT: {TOTAL_COST_PERCENT}%")

    # ═══ ۱) آمار Paper Trades ═══
    trades = load_from_github(PAPER_TRADES_FILE)
    if trades:
        stats = calculate_stats(trades)
        print(f"STATS: {stats}")

        if stats.get("closed", 0) > 0:
            net_emoji = "🟢" if stats["total_net"] > 0 else "🔴"
            signal_lines = ""
            for sig, s in stats.get("signal_stats", {}).items():
                wr = (s["wins"] / s["count"] * 100) if s["count"] > 0 else 0
                signal_lines += f"\n  {sig}: {s['count']} | برد {s['wins']} | {wr:.0f}%"

            msg = f"""📊 آمار Paper Trading

📈 کل: {stats['total']}
✅ بسته: {stats['closed']}
⏳ باز: {stats['open']}

🟢 برنده: {stats['wins']}
🔴 بازنده: {stats['losses']}
📊 Win Rate: {stats['win_rate']:.1f}%

💰 سود خام: {_fmt(stats['total_gross'])}
📉 هزینه: {_fmt(stats['total_costs'])}
{net_emoji} سود خالص: {_fmt(stats['total_net'])}

📈 میانگین برد: {_fmt(stats['avg_win'])}
📉 میانگین باخت: {_fmt(stats['avg_loss'])}
🎯 Expectancy: {_fmt(stats['expectancy'])}
📊 Profit Factor: {stats['profit_factor']:.2f}

📊 BUY: {stats['buys_count']} ({stats['buys_wins']} برد)
📊 SELL: {stats['sells_count']} ({stats['sells_wins']} برد)

📋 به تفکیک سیگنال:{signal_lines}"""
            send_message(msg)
        else:
            send_message(f"📊 آمار Paper Trading\n\n📈 کل: {stats['total']}\n⏳ باز: {stats['open']}\n\nℹ️ هنوز معامله‌ای بسته نشده.")

    # ═══ ۲) تحلیل آربیتراژ سه‌گانه ═══
    arb = analyze_all_pairs()
    if not arb:
        send_message("📊 تحلیل آربیتراژ\n\n❌ داده کافی نیست")
        return

    print(f"ARBITRAGE: {arb}")

    # خلاصه‌ی بهترین فرصت
    best_pair = None
    best_avg = -999
    for name in ["والکس → نوبیتکس", "نوبیتکس → والکس", "والکس → آبان", "آبان → والکس", "آبان → نوبیتکس", "نوبیتکس → آبان"]:
        r = arb.get(name)
        if r and r["avg_pct"] > best_avg:
            best_avg = r["avg_pct"]
            best_pair = name

    summary = ""
    if best_pair:
        summary = f"\n\n🎯 بهترین جفت: {best_pair}\n   میانگین: {best_avg:+.3f}%"
        if best_avg > TOTAL_COST_PERCENT:
            summary += f"\n   ✅ سوددهی دارد!"
        else:
            summary += f"\n   ❌ زیر هزینه ({TOTAL_COST_PERCENT}%)"

    msg = f"""📊 تحلیل آربیتراژ سه‌گانه
(والکس ↔ نوبیتکس ↔ آبان‌تتر)

📅 تعداد نمونه: {arb['count']}
💰 هزینه معامله: {TOTAL_COST_PERCENT}%

━━━━━━━━━━━━━━━━━━━━
🔄 والکس ↔ نوبیتکس
━━━━━━━━━━━━━━━━━━━━
{format_pair_report('والکس → نوبیتکس', arb.get('والکس → نوبیتکس'))}
{format_pair_report('نوبیتکس → والکس', arb.get('نوبیتکس → والکس'))}

━━━━━━━━━━━━━━━━━━━━
🔄 والکس ↔ آبان‌تتر
━━━━━━━━━━━━━━━━━━━━
{format_pair_report('والکس → آبان', arb.get('والکس → آبان'))}
{format_pair_report('آبان → والکس', arb.get('آبان → والکس'))}

━━━━━━━━━━━━━━━━━━━━
🔄 آبان‌تتر ↔ نوبیتکس
━━━━━━━━━━━━━━━━━━━━
{format_pair_report('آبان → نوبیتکس', arb.get('آبان → نوبیتکس'))}
{format_pair_report('نوبیتکس → آبان', arb.get('نوبیتکس → آبان'))}

━━━━━━━━━━━━━━━━━━━━
📊 اسپرد صرافی‌ها
━━━━━━━━━━━━━━━━━━━━

والکس: {arb.get('wallex_avg_spread', 0):.4f}%
آبان‌تتر: {arb.get('aban_avg_spread', 0):.4f}%
{summary}"""
    send_message(msg)


if __name__ == "__main__":
    main()
