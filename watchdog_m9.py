#!/usr/bin/env python3
# watchdog_m9.py — Read-only Watchdog for M9 (Priority) and M10 (HODL)
import os, sys, json, base64, time
from datetime import datetime, timezone
import requests

REPO       = os.environ.get("GH_REPO", "Ali212law/Price_bot")
GH_TOKEN   = os.environ.get("GH_TOKEN", "")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT  = os.environ.get("BALE_CHAT_ID", "")

M9_FILE = "paper_m9_trades.json"
M10_FILE = "paper_m10_trades.json"
WATCHDOG_STATE = "watchdog_m9_state.json"

THRESHOLD_MIN    = 90   # M9 هر ۱ ساعت اجرا می‌شود
REMIND_EVERY_MIN = 360  # حداکثر هر ۶ ساعت یادآوری

H = {"Authorization": "token %s" % GH_TOKEN}

def gh_get(path):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    try:
        r = requests.get(url, headers=H, timeout=30)
    except Exception as e:
        return None, "net:%s" % type(e).__name__
    if r.status_code == 404:
        return None, 404
    if r.status_code != 200:
        return None, r.status_code
    try:
        return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8")), 200
    except Exception as e:
        return None, "decode:%s" % type(e).__name__

def gh_put_state(data, tries=3):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, WATCHDOG_STATE)
    body = base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    for i in range(1, tries + 1):
        try:
            r = requests.get(url, headers=H, timeout=30)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload = {"message": "watchdog m9 state update", "content": body}
            if sha:
                payload["sha"] = sha
            r = requests.put(url, headers=H, json=payload, timeout=30)
            if r.status_code in (200, 201):
                return True
        except Exception:
            pass
        time.sleep(2 * i)
    return False

def bale_send(text, tries=3):
    if not BALE_TOKEN or not BALE_CHAT:
        print("BALE ERROR: Tokens missing")
        return False
    url = "https://tapi.bale.ai/bot%s/sendMessage" % BALE_TOKEN
    for i in range(1, tries + 1):
        try:
            r = requests.post(url, json={"chat_id": BALE_CHAT, "text": text}, timeout=30)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2 * i)
    return False

def parse_ts(s):
    if not s: return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def check_m9(nowdt):
    m9_data, status = gh_get(M9_FILE)
    if m9_data is None:
        return "M9 state unreadable (code=%s)" % status, True, 0
    
    ts = parse_ts(m9_data.get("last_run_utc"))
    if ts is None:
        return "M9 timestamp UNPARSEABLE", True, 0
    
    age = (nowdt - ts).total_seconds() / 60.0
    detail = "M9 | last_run=%s | age=%.0f min" % (ts.isoformat(), age)
    stale = (age > THRESHOLD_MIN)
    open_trades = len([t for t in m9_data.get("trades", []) if t.get("status") == "open"])
    return detail, stale, open_trades

def check_m10(nowdt):
    m10_data, status = gh_get(M10_FILE)
    if m10_data is None:
        return "M10 state unreadable", False, ""
    
    step = m10_data.get("step", 0)
    st = m10_data.get("status", "unknown")
    btc = m10_data.get("btc_amount", 0)
    return "M10 | status=%s | step=%d/3 | BTC=%.8f" % (st, step, btc), False, ""

def main():
    nowdt = datetime.now(timezone.utc)
    
    m9_detail, m9_stale, m9_open = check_m9(nowdt)
    m10_detail, _, _ = check_m10(nowdt)
    
    combined_detail = "%s\n%s" % (m9_detail, m10_detail)
    
    wd_state, _ = gh_get(WATCHDOG_STATE)
    if not isinstance(wd_state, dict): wd_state = {}
    prev = wd_state.get("status", "OK")
    sent = True
    
    if m9_stale and prev != "STALE":
        msg = "⚠️ واچ‌داگ M9+M10\n%s\nترید باز M9: %d" % (combined_detail, m9_open)
        sent = bale_send(msg)
        new_state = {"status": "STALE", "last_alert_utc": nowdt.isoformat()}
    elif m9_stale and prev == "STALE":
        lastA = parse_ts(wd_state.get("last_alert_utc"))
        since_last = ((nowdt - lastA).total_seconds() / 60.0) if lastA else REMIND_EVERY_MIN
        if since_last >= REMIND_EVERY_MIN:
            msg = "⚠️ واچ‌داگ M9+M10 — یادآوری\n%s\nترید باز M9: %d" % (combined_detail, m9_open)
            sent = bale_send(msg)
            new_state = {"status": "STALE", "last_alert_utc": nowdt.isoformat()}
        else:
            print("STALE persists but suppressed.")
            return
    elif not m9_stale and prev == "STALE":
        msg = "✅ واچ‌داگ — بازیابی\n%s" % combined_detail
        sent = bale_send(msg)
        new_state = {"status": "OK", "last_alert_utc": nowdt.isoformat()}
    else:
        print("OK — %s" % combined_detail)
        return

    gh_put_state(new_state)
    print("WATCHDOG ALERT-SENT status=%s" % new_state["status"])

if __name__ == "__main__":
    main()
