#!/usr/bin/env python3
# watchdog35.py — v1.1 | 2026-10-18 | AI سوم (هوشا)
import os, sys, json, base64, time
from datetime import datetime, timezone
import requests

REPO       = os.environ.get("GH_REPO", "Ali212law/Price_bot")
GH_TOKEN   = os.environ.get("GH_TOKEN", "")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_CHAT  = os.environ.get("BALE_CHAT_ID", "")
ANCHOR = "time_anchor35.json"
TRADES = "paper_trades35.json"
STATE  = "watchdog_state35.json"
THRESHOLD_MIN    = 90
REMIND_EVERY_MIN = 360
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
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, STATE)
    body = base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    for i in range(1, tries + 1):
        try:
            r = requests.get(url, headers=H, timeout=30)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload = {"message": "watchdog state update", "content": body}
            if sha:
                payload["sha"] = sha
            r = requests.put(url, headers=H, json=payload, timeout=30)
            if r.status_code in (200, 201):
                return True
            print("STATE PUT attempt %d failed: %s" % (i, r.status_code))
        except Exception as e:
            print("STATE PUT attempt %d error: %s" % (i, type(e).__name__))
        time.sleep(2 * i)
    return False

def bale_send(text, tries=3):
    if not BALE_TOKEN or not BALE_CHAT:
        print("BALE ERROR: BALE_BOT_TOKEN or BALE_CHAT_ID missing")
        return False
    url = "https://tapi.bale.ai/bot%s/sendMessage" % BALE_TOKEN
    for i in range(1, tries + 1):
        try:
            r = requests.post(url, json={"chat_id": BALE_CHAT, "text": text}, timeout=30)
            if r.status_code == 200:
                return True
            print("BALE WARN status=%s body=%s" % (r.status_code, str(r.text)[:150]))
        except Exception as e:
            print("BALE WARN %s: %s" % (type(e).__name__, e))
        time.sleep(2 * i)
    return False

def parse_ts(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def main():
    nowdt = datetime.now(timezone.utc)

    a, acode = gh_get(ANCHOR)
    if a is None:
        age = None
        detail = "anchor unreadable (code=%s)" % acode
    else:
        ts = parse_ts(a.get("last_run_utc") or a.get("last_run"))
        if ts is None:
            age = None
            detail = "anchor timestamp UNPARSEABLE"
        else:
            age = (nowdt - ts).total_seconds() / 60.0
            if age < 0:
                print("::warning::negative age (clock skew) — clamped to 0")
                age = 0.0
            detail = "last_run=%s | age=%.0f min" % (ts.isoformat(), age)

    t, _tc = gh_get(TRADES)
    trades = t if isinstance(t, list) else []
    open_tr = [x for x in trades if isinstance(x, dict)
               and str(x.get("status", "")).lower() == "open"]

    def open_info():
        if not open_tr:
            return "ترید باز: ۰"
        lines = ["ترید باز: %d (خطر گم‌شدن exit در صورت ادامه قطعی ذخیره)" % len(open_tr)]
        for x in open_tr:
            et = parse_ts(x.get("entry_time") or x.get("time"))
            hrs = ((nowdt - et).total_seconds() / 3600.0) if et else None
            lines.append("  entry=%s | RSI=%s | مدت باز: %s ساعت" % (
                x.get("entry_time"), x.get("rsi_at_entry"),
                ("%.1f" % hrs) if hrs is not None else "?"))
        return "\n".join(lines)

    stale = (age is None) or (age > THRESHOLD_MIN)

    st, _sc = gh_get(STATE)
    state = st if isinstance(st, dict) else {}
    prev = str(state.get("status", "OK"))
    sent = True

    if stale and prev != "STALE":
        msg = ("⚠️ واچ‌داگ Paper35\nذخیره قطع است: %s (آستانه %d دقیقه)\n%s\nهشدار شماره: ۱"
               % (detail, THRESHOLD_MIN, open_info()))
        sent = bale_send(msg)
        new_state = {"status": "STALE", "alerts_sent": 1,
                     "stale_since_utc": nowdt.isoformat(),
                     "last_alert_utc": nowdt.isoformat()}
    elif stale and prev == "STALE":
        lastA = parse_ts(state.get("last_alert_utc"))
        since_last = ((nowdt - lastA).total_seconds() / 60.0) if lastA else REMIND_EVERY_MIN
        if since_last >= REMIND_EVERY_MIN:
            n = int(state.get("alerts_sent", 0)) + 1
            msg = ("⚠️ واچ‌داگ Paper35 — یادآوری\nهنوز قطع است: %s\n%s\nهشدار شماره: %d"
                   % (detail, open_info(), n))
            sent = bale_send(msg)
            new_state = dict(state)
            new_state["alerts_sent"] = n
            new_state["last_alert_utc"] = nowdt.isoformat()
        else:
            print("STALE persists but reminder suppressed (%.0f min < %d min)"
                  % (since_last, REMIND_EVERY_MIN))
            print("WATCHDOG OK (suppressed)")
            return
    elif (not stale) and prev == "STALE":
        sinceS = parse_ts(state.get("stale_since_utc"))
        dur = ((nowdt - sinceS).total_seconds() / 3600.0) if sinceS else None
        msg = ("✅ واچ‌داگ Paper35 — بازیابی\n%s\nمدت قطعی: %s ساعت\nتعداد هشدارهای صادرشده: %s"
               % (detail, ("%.1f" % dur) if dur is not None else "?",
                  state.get("alerts_sent", 0)))
        sent = bale_send(msg)
        new_state = {"status": "OK", "alerts_sent": 0,
                     "stale_since_utc": None, "last_alert_utc": nowdt.isoformat()}
    else:
        print("OK — %s | trades=%d open=%d | no message needed"
              % (detail, len(trades), len(open_tr)))
        print("WATCHDOG OK")
        return

    if not gh_put_state(new_state):
        print("WATCHDOG FAIL: state not persisted — reminders may repeat")
        sys.exit(1)
    if not sent:
        print("WATCHDOG FAIL: alert could not be delivered to Bale")
        sys.exit(1)
    print("WATCHDOG ALERT-SENT status=%s" % new_state.get("status"))

if __name__ == "__main__":
    main()
