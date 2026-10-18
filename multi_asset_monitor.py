#!/usr/bin/env python3
"""
multi_asset_monitor.py — M6 Phase 1: Multi-Asset Data Collection
- Fetches OHLCV and RSI for ETH, SOL, XRP from Wallex.
- Logs to multi_asset_history.json (keeps last 7 days).
"""
import os
import json
import base64
import requests
import time
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
HISTORY_FILE = "multi_asset_history.json"
MAX_RECORDS = 672  # 7 days of 15-min intervals
TARGET_ASSETS = ["ETH", "SOL", "XRP"]

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return [], None
    except Exception:
        return [], None

def save_to_github(filename, data, sha=None):
    try:
        if not sha:
            _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"SAVE ERROR ({filename}): {e}")
        return False

def calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def fetch_asset_ohlcv(symbol):
    for quote in ["USDT", "TMN"]:
        pair = f"{symbol}{quote}"
        now = int(time.time())
        start = now - (48 * 3600)
        url = f"https://api.wallex.ir/v1/udf/history?symbol={pair}&resolution=15&from={start}&to={now}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get('s') == 'ok' and len(data.get('c', [])) > 14:
                    closes = [float(c) for c in data['c']]
                    last_idx = -1
                    # ذخیره آخرین کندل کامل به همراه RSI
                    candle = {
                        "t": int(data['t'][last_idx]),
                        "o": float(data['o'][last_idx]),
                        "h": float(data['h'][last_idx]),
                        "l": float(data['l'][last_idx]),
                        "c": closes[last_idx],
                        "v": float(data['v'][last_idx]),
                        "rsi": calculate_rsi(closes)
                    }
                    return {"pair": pair, "candle": candle}
        except Exception:
            pass
    return None

def main():
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {"time": now, "assets": {}}
    
    for symbol in TARGET_ASSETS:
        data = fetch_asset_ohlcv(symbol)
        if data:
            snapshot["assets"][symbol] = data
            print(f"{symbol}: C={data['candle']['c']:,.2f} | RSI={data['candle']['rsi']} | Vol={data['candle']['v']}")
        else:
            print(f"{symbol}: Failed to fetch.")

    if not snapshot["assets"]:
        return

    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, list): history = []
    history.append(snapshot)
    if len(history) > MAX_RECORDS: history = history[-MAX_RECORDS:]

    if save_to_github(HISTORY_FILE, history, sha):
        print("OHLCV History saved.")

if __name__ == "__main__":
    main()
