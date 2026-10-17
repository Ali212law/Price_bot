#!/usr/bin/env python3
"""
shadow_lab.py — Parallel Hypothesis Testing (Shadow Only)
Runs every 1 hour. Does NOT interact with Paper 34 or Paper 35.
Tests: Arbitrage Gap, Bollinger Breakout, Weekend Effect, Iran News Veto.
"""
import requests
import json
import os
import base64
import time
from datetime import datetime, timedelta, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = "Ali212law/Price_bot"
LAB_FILE = "shadow_lab_trades.json"
BTC_HISTORY_FILE = "btc_history.json"
IRAN_NEWS_FILE = "iran_news_data.json"

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return None, None
    except: return None, None

def save_to_github(filename, data, sha=None):
    try:
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def get_prices():
    try:
        # Wallex BTC/TMN
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=10)
        symbols = r.json().get("result", {}).get("symbols", {})
        btc_tmn = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        usdt_tmn = float(symbols.get("USDTTMN", {}).get("stats", {}).get("lastPrice", 0))
        if btc_tmn > 100_000_000_000: btc_tmn /= 10
        if usdt_tmn > 1_000_000: usdt_tmn /= 10
        
        # Binance BTC/USDT
        rb = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": "BTCUSDT"}, timeout=10)
        btc_usdt = float(rb.json().get("price", 0))
        
        return {"btc_tmn": btc_tmn, "usdt_tmn": usdt_tmn, "btc_usdt": btc_usdt}
    except Exception as e:
        print(f"Price fetch error: {e}")
        return None

def get_rsi():
    try:
        # We read from btc_history to calculate a quick RSI
        data, _ = load_from_github(BTC_HISTORY_FILE)
        if not data or len(data) < 15: return 50.0
        closes = [p for t, p in data[-20:]]
        gains, losses = [], []
        for i in range(1, len(closes)):
            ch = closes[i] - closes[i-1]
            if ch > 0: gains.append(ch); losses.append(0)
            else: gains.append(0); losses.append(abs(ch))
        ag = sum(gains[-14:]) / 14
        al = sum(losses[-14:]) / 14
        return 100 - (100 / (1 + (ag/al))) if al > 0 else 100
    except: return 50.0

def get_iran_sentiment():
    data, _ = load_from_github(IRAN_NEWS_FILE)
    if not data: return "unclear"
    stats = data.get("stats", {}) if isinstance(data, dict) else {}
    if stats and "by_btc_impact" in stats:
        up, down = stats["by_btc_impact"].get("up", 0), stats["by_btc_impact"].get("down", 0)
        if up > down * 2 and up >= 3: return "bullish"
        if down > up * 2 and down >= 3: return "bearish"
    return "neutral"

def calculate_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period: return None, None, None
    sma = sum(closes[-period:]) / period
    variance = sum((x - sma) ** 2 for x in closes[-period:]) / period
    std = variance ** 0.5
    return sma, sma + (std * std_dev), sma - (std * std_dev)

def main():
    print("=== SHADOW LAB ===")
    prices = get_prices()
    if not prices: return
    
    btc_tmn = prices["btc_tmn"]
    usdt_tmn = prices["usdt_tmn"]
    btc_usdt = prices["btc_usdt"]
    
    rsi = get_rsi()
    iran_sent = get_iran_sentiment()
    now = datetime.now(timezone.utc)
    
    # 1. Arbitrage Gap
    implied = btc_usdt * usdt_tmn
    gap_pct = ((implied - btc_tmn) / btc_tmn) * 100 if btc_tmn > 0 else 0
    
    # 2. Bollinger Bands
    data, sha = load_from_github(BTC_HISTORY_FILE)
    closes = [p for t, p in data[-30:]] if data else []
    sma, upper, lower = calculate_bollinger(closes)
    
    # Load Lab Log
    lab_log, lab_sha = load_from_github(LAB_FILE)
    if not lab_log: lab_log = []
    
    timestamp = now.isoformat()
    new_entries = []
    
    # Evaluate Hypotheses (Only log if conditions met, to save space)
    if gap_pct > 1.0:
        new_entries.append({"time": timestamp, "strategy": "H1_ArbGap", "side": "buy", "price": btc_tmn, "reason": f"Gap {gap_pct:.2f}%"})
    elif gap_pct < -1.0:
        new_entries.append({"time": timestamp, "strategy": "H1_ArbGap", "side": "sell", "price": btc_tmn, "reason": f"Gap {gap_pct:.2f}%"})
        
    if upper and closes and closes[-1] > upper:
        new_entries.append({"time": timestamp, "strategy": "H2_Bollinger", "side": "buy", "price": btc_tmn, "reason": "Close > Upper Band"})
    elif lower and closes and closes[-1] < lower:
        new_entries.append({"time": timestamp, "strategy": "H2_Bollinger", "side": "sell", "price": btc_tmn, "reason": "Close < Lower Band"})
        
    if rsi < 30 and now.weekday() in [4, 5]: # Friday=4, Saturday=5 in UTC (Iran weekend)
        new_entries.append({"time": timestamp, "strategy": "H3_WeekendDip", "side": "buy", "price": btc_tmn, "reason": f"RSI {rsi:.1f} on Weekend"})
        
    if rsi < 30 and iran_sent != "bearish":
        new_entries.append({"time": timestamp, "strategy": "H4_IranVeto", "side": "buy", "price": btc_tmn, "reason": f"RSI {rsi:.1f}, Iran={iran_sent}"})
        
    if new_entries:
        lab_log.extend(new_entries)
        # Keep last 500 entries
        lab_log = lab_log[-500:]
        save_to_github(LAB_FILE, lab_log, lab_sha)
        print(f"Logged {len(new_entries)} new shadow signals.")
        for e in new_entries: print(f"  {e['strategy']} -> {e['side']} @ {e['price']:,.0f}")
    else:
        print("No new signals matched.")

if __name__ == "__main__":
    main()
