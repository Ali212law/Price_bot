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

bot = Client(BALE_TOKEN)

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

def load_from_github(filename):
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
        r = requests.post(url, data=params, timeout=30)
        return r.json()
    except Exception as e:
        print(f"SEND ERROR: {e}")
        return None

def calculate_stats(trades):
    """محاسبه آمار کامل Paper Trading"""
    if not trades:
        return None
    
    closed = [t for t in trades if t.get("status") == "closed"]
    open_trades = [t for t in trades if t.get("status") == "open"]
    
    if not closed:
        return {
            "total": len(trades),
            "closed": 0,
            "open": len(open_trades),
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_profit": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "expectancy": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "best_trade": 0,
            "worst_trade": 0
        }
    
    wins = [t for t in closed if t.get("profit_toman", 0) > 0]
    losses = [t for t in closed if t.get("profit_toman", 0) < 0]
    
    total_profit = sum(t.get("profit_toman", 0) for t in closed)
    total_wins = sum(t.get("profit_toman", 0) for t in wins)
    total_losses = abs(sum(t.get("profit_toman", 0) for t in losses))
    
    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0
    
    win_rate = len(wins) / len(closed) if closed else 0
    loss_rate = len(losses) / len(closed) if closed else 0
    
    # Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    
    # Profit Factor = Total Wins / Total Losses
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
    
    # Max Drawdown
    sorted_trades = sorted(closed, key=lambda x: x.get("time", ""))
    balance = 0
    peak = 0
    max_dd = 0
    for t in sorted_trades:
        balance += t.get("profit_toman", 0)
        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd
    
    best_trade = max([t.get("profit_toman", 0) for t in closed], default=0)
    worst_trade = min([t.get("profit_toman", 0) for t in closed], default=0)
    
    return {
        "total": len(trades),
        "closed": len(closed),
        "open": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate * 100,
        "total_profit": total_profit,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "best_trade": best_trade,
        "worst_trade": worst_trade
    }

def format_stats(stats):
    """فرمت آمار برای ارسال به بله"""
    if not stats:
        return "📊 آمار Paper Trading\n\n❌ هیچ معامله‌ای یافت نشد."
    
    if stats["closed"] == 0:
        return f"""📊 آمار Paper Trading

📈 کل معاملات: {stats['total']}
⏳ باز: {stats['open']}
✅ بسته‌شده: 0

ℹ️ هنوز معامله‌ای بسته نشده.
منتظر حد ضرر یا حد سود هستیم."""
    
    msg = f"""📊 آمار کامل Paper Trading

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 معاملات:
   کل: {stats['total']}
   ✅ بسته: {stats['closed']}
   ⏳ باز: {stats['open']}

🎯 نتایج:
   🟢 برنده: {stats['wins']}
   🔴 بازنده: {stats['losses']}
   📊 Win Rate: {stats['win_rate']:.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 سود/ضرر:
   💵 کل سود/ضرر: {stats['total_profit']:,.0f} تومان
   🟢 کل سود: {stats['total_wins']:,.0f}
   🔴 کل ضرر: {stats['total_losses']:,.0f}

📊 میانگین‌ها:
   🟢 میانگین سود: {stats['avg_win']:,.0f}
   🔴 میانگین ضرر: {stats['avg_loss']:,.0f}
   📈 Expectancy: {stats['expectancy']:,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📉 Profit Factor: {stats['profit_factor']:.2f}
📉 Max Drawdown: {stats['max_drawdown']:,.0f} تومان
🏆 بهترین معامله: {stats['best_trade']:,.0f}
❌ بدترین معامله: {stats['worst_trade']:,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 ارزیابی:
"""
    
    if stats['expectancy'] > 0:
        msg += "✅ Expectancy مثبت - استراتژی سودده\n"
    else:
        msg += "❌ Expectancy منفی - استراتژی ضررده\n"
    
    if stats['profit_factor'] > 1.5:
        msg += "✅ Profit Factor خوب (>1.5)\n"
    elif stats['profit_factor'] > 1:
        msg += "⚠️ Profit Factor متوسط (1-1.5)\n"
    else:
        msg += "❌ Profit Factor ضعیف (<1)\n"
    
    if stats['win_rate'] > 55:
        msg += "✅ Win Rate خوب (>55%)\n"
    elif stats['win_rate'] > 45:
        msg += "⚠️ Win Rate متوسط (45-55%)\n"
    else:
        msg += "❌ Win Rate ضعیف (<45%)\n"
    
    return msg

def main():
    print("=== ANALYZE PAPER TRADING ===")
    
    trades = load_from_github(PAPER_TRADES_FILE)
    
    if not trades:
        print("NO PAPER TRADES FILE")
        send_message("📊 آمار Paper Trading\n\n❌ هنوز فایلی وجود نداره.")
        return
    
    print(f"TOTAL TRADES: {len(trades)}")
    
    stats = calculate_stats(trades)
    print(f"STATS: {stats}")
    
    msg = format_stats(stats)
    send_message(msg)
    print("REPORT SENT")

if __name__ == "__main__":
    main()
