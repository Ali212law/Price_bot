#!/usr/bin/env python3
"""
bitpin_monitor.py — M5 Phase 1: Data collection from Bitpin Exchange
- Fetches BTC/IRT price every 15 mins.
- Logs to bitpin_history.json (keeps last 7 days).
- Read-only on Bitpin; writes only to its own history file.
"""
import os
import json
import base64
import requests
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
HISTORY_FILE = "bitpin_history.json"
MAX_RECORDS = 672  # 7 days of 15-min intervals

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

def fetch_bitpin_price():
    # Bitpin public API for tickers
    url = "https://api.bitpin.ir/api/v1/mkt/tickers/"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                if item.get("symbol") == "BTC_IRT":
                    return float(item.get("last", 0))
    except Exception as e:
        print(f"FETCH ERROR: {e}")
    return None

def main():
    now = datetime.now(timezone.utc).isoformat()
    price = fetch_bitpin_price()
    
    if price is None or price == 0:
        print("Could not fetch Bitpin price.")
        return

    print(f"Bitpin BTC/IRT: {price:,.0f} at {now}")

    history, sha = load_from_github(HISTORY_FILE)
    if not isinstance(history, list):
        history = []

    history.append({"time": now, "price": price})
    
    # Keep only the last MAX_RECORDS
    if len(history) > MAX_RECORDS:
        history = history[-MAX_RECORDS:]

    if save_to_github(HISTORY_FILE, history, sha):
        print("History saved successfully.")
    else:
        print("Failed to save history.")

if __name__ == "__main__":
    main()
