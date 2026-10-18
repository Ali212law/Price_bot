#!/usr/bin/env python3
import os, sys, json, base64
from datetime import datetime, timezone
import requests

REPO = os.environ.get("GH_REPO", "Ali212law/Price_bot")
TOKEN = os.environ.get("GH_TOKEN", "")
ANCHOR = "time_anchor35.json"
THRESHOLD_MIN = 90

def gh_get(path):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    r = requests.get(url, headers={"Authorization": "token %s" % TOKEN}, timeout=30)
    if r.status_code != 200:
        return None, r.status_code
    try:
        return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8")), 200
    except Exception as e:
        return None, str(e)

def main():
    print("=== VERIFY PERSISTENCE (D.2) ===")
    anchor, status = gh_get(ANCHOR)
    
    # Fixed by AI3: handle empty dict
    if anchor is None or status != 200:
        print("::error::Cannot fetch %s from remote. Status: %s" % (ANCHOR, status))
        sys.exit(1)

    print("Remote anchor content: %s" % json.dumps(anchor))
    last_run = anchor.get("last_run_utc") or anchor.get("last_run")
    if not last_run:
        print("::error::No timestamp found in anchor.")
        sys.exit(1)

    try:
        ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception as e:
        print("::error::Failed to parse timestamp: %s" % e)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    age_min = (now - ts).total_seconds() / 60.0
    print("Anchor age: %.1f minutes (Threshold: %d)" % (age_min, THRESHOLD_MIN))

    if age_min > THRESHOLD_MIN:
        print("::error::anchor35 is STALE! Persistence failure suspected.")
        sys.exit(1)

    print("VERIFY OK: anchor is fresh.")
    sys.exit(0)

if __name__ == "__main__":
    main()
