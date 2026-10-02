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
PRICE_COMPARISON_FILE = "price_comparison.json"
NEWS_HISTORY_FILE = "news_history.json"
VETO_LOG_FILE = "veto_log.json"

FEE_PER_SIDE = 0.25
FEE_ROUND_TRIP = FEE_PER_SIDE * 2
SLIPPAGE_PER_SIDE = 0.05
SLIPPAGE_ROUND_TRIP = SLIPPAGE_PER_SIDE * 2
TOTAL_COST_PERCENT = FEE_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

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
        except Exception as e:
            print(f"RETRY: {e}")
        if attempt < max_retries - 1:
            time.sleep(3 ** attempt)
    return None


def load_from_github(filename, silent_404=True):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = request_with_retry(url, headers=headers)
        if r and r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content)
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


def calc_stats(trades, label=""):
    """آمار کلی از یه لیست معاملات"""
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

    win_rate = len(wins) / len(closed) * 100 if closed else 0
    expectancy = total_net / len(closed) if closed else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

    # به تفکیک سیگنال
    signal_stats = {}
    for t in closed:
        sig = t.get("signal_type", "?")
        if sig not in signal_stats:
            signal_stats[sig] = {"count": 0, "wins": 0, "net": 0}
        signal_stats[sig]["count"] += 1
        signal_stats[sig]["net"] += t.get("profit_net_toman", 0)
        if t.get("profit_net_toman", 0) > 0:
            signal_stats[sig]["wins"] += 1

    # به تفکیک side
    buys = [t for t in closed if t.get("side") == "buy"]
    sells = [t for t in closed if t.get("side") == "sell"]
    buys_wins = [t for t in buys if t.get("profit_net_toman", 0) > 0]
    sells_wins = [t for t in sells if t.get("profit_net_toman", 0) > 0]

    return {
        "total": len(trades),
        "closed": len(closed),
        "open": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_gross": total_gross,
        "total_net": total_net,
        "total_costs": total_costs,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "signal_stats": signal_stats,
        "buys_count": len(buys),
        "buys_wins": len(buys_wins),
        "sells_count": len(sells),
        "sells_wins": len(sells_wins),
    }


def analyze_news_history():
    data = load_from_github(NEWS_HISTORY_FILE)
    if not data:
        return None

    total = len(data)
    sentiments = {"positive": 0, "negative": 0, "neutral": 0}
    for d in data:
        s = d.get("sentiment", "neutral")
        if s in sentiments:
            sentiments[s] += 1

    return {
        "total_samples": total,
        "positive": sentiments["positive"],
        "negative": sentiments["negative"],
        "neutral": sentiments["neutral"],
    }


def analyze_veto_log():
    data = load_from_github(VETO_LOG_FILE)
    if not data:
        return None
    return {"total_vetos": len(data)}


def main():
    print("=== ANALYZE 5 (Paper vs Shadow) ===")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"TOTAL_COST_PERCENT: {TOTAL_COST_PERCENT}%")

    # === Paper Stats ===
    paper_trades = load_from_github(PAPER_TRADES_FILE) or []
    paper_stats = calc_stats(paper_trades, "Paper")
    print(f"PAPER STATS: {paper_stats}")

    # === Shadow Stats ===
    shadow_trades = load_from_github(SHADOW_TRADES_FILE) or []
    shadow_stats = calc_stats(shadow_trades, "Shadow")
    print(f"SHADOW STATS: {shadow_stats}")

    # === Shadow به تفکیک نوع ===
    veto_shadows = [s for s in shadow_trades if s.get("shadow_type") == "veto"]
    top_shadows = [s for s in shadow_trades if s.get("shadow_type") == "top_only"]

    veto_stats = calc_stats(veto_shadows, "Veto Shadow")
    top_stats = calc_stats(top_shadows, "TOP Shadow")

    # === News Stats ===
    news_stats = analyze_news_history()
    veto_log = analyze_veto_log()

    # ═══ پیام اصلی ═══
    if paper_stats and paper_stats.get("closed", 0) > 0:
        net_emoji = "🟢" if paper_stats["total_net"] > 0 else "🔴"

        signal_lines = ""
        for sig, s in paper_stats.get("signal_stats", {}).items():
            wr = (s["wins"] / s["count"] * 100) if s["count"] > 0 else 0
            signal_lines += f"\n  {sig}: {s['count']} | برد {s['wins']} | {wr:.0f}% | {_fmt(s['net'])}"

        msg = f"""📊 آمار Paper Trades

📈 کل: {paper_stats['total']}
✅ بسته: {paper_stats['closed']}
⏳ باز: {paper_stats['open']}

🟢 برنده: {paper_stats['wins']}
🔴 بازنده: {paper_stats['losses']}
📊 Win Rate: {paper_stats['win_rate']:.1f}%

💰 خام: {_fmt(paper_stats['total_gross'])}
📉 هزینه: {_fmt(paper_stats['total_costs'])}
{net_emoji} خالص: {_fmt(paper_stats['total_net'])}

📈 میانگین برد: {_fmt(paper_stats['avg_win'])}
📉 میانگین باخت: {_fmt(paper_stats['avg_loss'])}
🎯 Expectancy: {_fmt(paper_stats['expectancy'])}
📊 Profit Factor: {paper_stats['profit_factor']:.2f}

📊 BUY: {paper_stats['buys_count']} ({paper_stats['buys_wins']} برد)
📊 SELL: {paper_stats['sells_count']} ({paper_stats['sells_wins']} برد)

📋 به تفکیک سیگنال:{signal_lines}"""
        send_message(msg)

    # ═══ پیام Shadow ═══
    if shadow_stats and shadow_stats.get("closed", 0) > 0:
        net_emoji = "🟢" if shadow_stats["total_net"] > 0 else "🔴"

        msg = f"""👻 آمار Shadow Trades

📈 کل: {shadow_stats['total']}
✅ بسته: {shadow_stats['closed']}
⏳ باز: {shadow_stats['open']}

🟢 برنده: {shadow_stats['wins']}
🔴 بازنده: {shadow_stats['losses']}
📊 Win Rate: {shadow_stats['win_rate']:.1f}%

{net_emoji} سود/ضرر خالص: {_fmt(shadow_stats['total_net'])}

━━━━━━━━━━━━━━━━━━━━
🔴 Veto Shadows (رد شده)
━━━━━━━━━━━━━━━━━━━━"""
        if veto_stats and veto_stats.get("closed", 0) > 0:
            msg += f"""
✅ بسته: {veto_stats['closed']}
📊 Win Rate: {veto_stats['win_rate']:.1f}%
💰 خالص: {_fmt(veto_stats['total_net'])}"""
        else:
            msg += f"\n⏳ هنوز بسته نشده ({len(veto_shadows)} باز)"

        msg += f"""

━━━━━━━━━━━━━━━━━━━━
🎯 TOP Shadows (فقط TOP)
━━━━━━━━━━━━━━━━━━━━"""
        if top_stats and top_stats.get("closed", 0) > 0:
            msg += f"""
✅ بسته: {top_stats['closed']}
📊 Win Rate: {top_stats['win_rate']:.1f}%
💰 خالص: {_fmt(top_stats['total_net'])}"""
        else:
            msg += f"\n⏳ هنوز بسته نشده ({len(top_shadows)} باز)"

        send_message(msg)

    # ═══ تحلیل Veto ═══
    if veto_stats and veto_stats.get("closed", 0) > 0:
        # اگه veto خوب بوده (ضرر جلوگیری شده) → shadow منفی می‌شد
        # پس shadow مثبت = veto اشتباه بوده
        veto_net = veto_stats["total_net"]
        if veto_net > 0:
            verdict = f"❌ Veto اشتباه بوده (سود از دست رفت: {_fmt(veto_net)})"
        elif veto_net < 0:
            verdict = f"✅ Veto درست بوده (ضرر جلوگیری شد: {_fmt(abs(veto_net))})"
        else:
            verdict = "⚪ Veto بی‌اثر بوده"

        msg = f"""🎯 تحلیل Veto

📊 تعداد Veto: {len(veto_shadows)}
✅ بسته: {veto_stats['closed']}
📊 Win Rate (Shadow): {veto_stats['win_rate']:.1f}%
💰 سود/ضرر Shadow: {_fmt(veto_net)}

{verdict}"""
        send_message(msg)

    # ═══ آمار کلی ═══
    if news_stats or veto_log:
        news_line = ""
        if news_stats:
            news_line = (
                f"\n📰 اخبار ({news_stats['total_samples']} نمونه):\n"
                f"  ✅ مثبت: {news_stats['positive']}\n"
                f"  ❌ منفی: {news_stats['negative']}\n"
                f"  ⚪ خنثی: {news_stats['neutral']}"
            )

        veto_line = ""
        if veto_log:
            veto_line = f"\n\n🚫 Vetoهای ثبت‌شده: {veto_log['total_vetos']}"

        msg = f"""📊 آمار کلی{news_line}{veto_line}"""
        send_message(msg)


if __name__ == "__main__":
    main()
