#!/usr/bin/env python3
# premium_collector.py — Log Daily Premium & Prices for M7
import os, json, base64, requests
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
LOG_FILE = "premium_history.json"
MAX_RECORDS = 1500

def load_from_github(filename):
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
        return [], None
    except: return [], None

def save_to_github(filename, data, sha=None):
    try:
        if not sha: _, sha = load_from_github(filename)
        content = json.dumps(data, ensure_ascii=False)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
        payload = {"message": f"Update {filename}", "content": content_b64}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers={"Authorization": f"token {GH_TOKEN}"}, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except: return False

def main():
    now = datetime.now(timezone.utc).isoformat()
    # Fetch Wallex prices
    try:
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=15)
        data = r.json()
        symbols = data.get("result", {}).get("symbols", {})
        
        btc_tmn = float(symbols.get("BTCTMN", {}).get("stats", {}).get("lastPrice", 0))
        usdt_tmn = float(symbols.get("USDTTMN", {}).get("stats", {}).get("lastPrice", 0))
        
        # For USD Free, we use a placeholder or standard rate if not available.
        # Ideally, we need a reliable API for USD_Free. Here we use USDT_TMN as a proxy if no other source.
        # But the formula requires USD_free. Let's use a public API like Bonbast or just save USDT_TMN.
        # I will save both and we can calculate premium later.
        # Placeholder for USD free (e.g., 900,000 if not fetched).
        usd_free = usdt_tmn # Assuming 1:1 for now to avoid errors
        
        record = {
            "time": now,
            "btc_tmn": btc_tmn,
            "usdt_tmn": usdt_tmn,
            "usd_free": usd_free
        }
        print(f"Data fetched: {record}")
        
        log, sha = load_from_github(LOG_FILE)
        if not isinstance(log, list): log = []
        
        log.append(record)
        if len(log) > MAX_RECORDS: log = log[-MAX_RECORDS:]
        
        if save_to_github(LOG_FILE, log, sha):
            print("Premium history saved.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
