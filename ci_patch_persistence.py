#!/usr/bin/env python3
import re, sys, io

SRC_FILE = "paper_trade35.py"

NEW_FUNC = '''def save_to_github(filename, data, sha=None):
    # PATCHED (ci_patch_persistence v1.0)
    import time as _t, requests as _rq
    headers = {"Authorization": f"token {GH_TOKEN}"}
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{filename}"
    try:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        print(f"PERSIST file={filename} status=FAIL error=encode {type(e).__name__}: {e}")
        return False
    content = base64.b64encode(body).decode("utf-8")
    last_err = "unknown"
    for attempt in range(1, 4):
        try:
            if not sha:
                r = _rq.get(url, headers=headers, timeout=30)
                if r.status_code == 200:
                    sha = r.json().get("sha")
                elif r.status_code == 404:
                    sha = None
                else:
                    last_err = "GET sha %s" % r.status_code
                    _t.sleep(3 * attempt); continue
            payload = {"message": "Update %s" % filename, "content": content}
            if sha:
                payload["sha"] = sha
            r = _rq.put(url, headers=headers, json=payload, timeout=30)
            if r.status_code in (200, 201):
                rv = _rq.get(url, headers=headers, timeout=30)
                if rv.status_code == 200:
                    remote = json.loads(base64.b64decode(rv.json()["content"]).decode("utf-8"))
                    if json.dumps(remote, sort_keys=True) == json.dumps(data, sort_keys=True):
                        print("PERSIST file=%s status=OK attempt=%d" % (filename, attempt))
                        return True
                    last_err = "verify mismatch"
                else:
                    last_err = "verify GET %s" % rv.status_code
            elif r.status_code in (409, 422):
                last_err = "PUT %s sha-conflict" % r.status_code
                sha = None
            else:
                last_err = "PUT %s: %s" % (r.status_code, str(r.text)[:180])
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, e)
        _t.sleep(3 * attempt)
    print("PERSIST file=%s status=FAIL error=%s" % (filename, last_err))
    try:
        with open("persist_fail.marker", "a", encoding="utf-8") as mf:
            mf.write("%s\t%s\n" % (filename, last_err))
    except Exception:
        pass
    return False
'''

FUNC_RE = re.compile(r"def save_to_github\(.*?except: return False", re.DOTALL)
CALL_RE = re.compile(r'([ \t]+)save_to_github\(TIME_ANCHOR_FILE, anchor\)\n([ \t]+)print\("TIME_ANCHOR SAVED"\)')

def main():
    try:
        with io.open(SRC_FILE, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        print("PATCH ERROR cannot read %s: %s" % (SRC_FILE, e))
        sys.exit(1)
    if "PATCHED (ci_patch_persistence" in src:
        print("PATCH already applied — skip")
        return
    src2, n_func = FUNC_RE.subn(lambda m: NEW_FUNC, src, count=1)
    if n_func != 1:
        print("PATCH_MISSED: save_to_github pattern not found — repo file left untouched")
        return
    def _call_fix(m):
        ind1, ind2 = m.group(1), m.group(2)
        return (ind1 + '_ok = save_to_github(TIME_ANCHOR_FILE, anchor)\n'
                + ind2 + 'print("TIME_ANCHOR SAVED" if _ok else "TIME_ANCHOR FAILED")')
    src2, n_call = CALL_RE.subn(_call_fix, src2, count=1)
    with io.open(SRC_FILE, "w", encoding="utf-8") as f:
        f.write(src2)
    print("PATCH APPLIED: save_to_github replaced | call-site:",
          "patched" if n_call == 1 else "MISSED (function still writes marker on failure)")
    sys.exit(0)

if __name__ == "__main__":
    main()
