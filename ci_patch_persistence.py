#!/usr/bin/env python3
# ci_patch_persistence.py — v2.0 | 2026-10-18 | AI سوم (هوشا)
# کل save_to_github را در workspace با نسخه مقاوم جایگزین می‌کند.
# فایل ریپو دست‌نخورده می‌ماند. اگر الگو پیدا نشد: PATCH_MISSED + exit 0.
import re, sys, io

SRC_FILE = "paper_trade35.py"
MARKER = "PATCHED (ci_patch_persistence v2.0)"

NEW_FUNC = '''def save_to_github(filename, data, sha=None):
    # PATCHED (ci_patch_persistence v2.0): fresh-sha fetch, 409/422 conflict
    # handling, retry, verify-after-write, loud failure + marker for CI gate.
    import time as _t, requests as _rq
    try:
        _tok, _rep = GH_TOKEN, GH_REPO
    except NameError:
        import os as _os
        _tok = _os.environ.get("GH_TOKEN", "")
        _rep = _os.environ.get("GH_REPO", "Ali212law/Price_bot")
    _headers = {"Authorization": "token %s" % _tok}
    _url = "https://api.github.com/repos/%s/contents/%s" % (_rep, filename)
    try:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        print("PERSIST file=%s status=FAIL error=encode %s: %s" % (filename, type(e).__name__, e))
        _write_marker(filename, "encode %s" % e)
        return False
    content = base64.b64encode(body).decode("utf-8")
    last_err = "unknown"
    for attempt in range(1, 4):
        try:
            if not sha:
                r = _rq.get(_url, headers=_headers, timeout=30)
                if r.status_code == 200:
                    sha = r.json().get("sha")
                elif r.status_code == 404:
                    sha = None
                else:
                    last_err = "GET sha %s" % r.status_code
                    _t.sleep(2 * attempt); continue
            payload = {"message": "Update %s" % filename, "content": content}
            if sha:
                payload["sha"] = sha
            r = _rq.put(_url, headers=_headers, json=payload, timeout=30)
            if r.status_code in (200, 201):
                rv = _rq.get(_url, headers=_headers, timeout=30)
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
        _t.sleep(2 * attempt)
    print("PERSIST file=%s status=FAIL error=%s" % (filename, last_err))
    _write_marker(filename, last_err)
    return False


def _write_marker(filename, err):
    try:
        with open("persist_fail.marker", "a", encoding="utf-8") as mf:
            mf.write("%s\\t%s\\n" % (filename, err))
    except Exception:
        pass
'''

FUNC_RE = re.compile(r"def save_to_github\(.*?(?=\ndef |\nclass |\n#|\Z)", re.DOTALL)
CALL_RE = re.compile(
    r"([ \t]*)save_to_github\(\s*TIME_ANCHOR_FILE\s*,\s*anchor\s*(?:,[^)\n]*)?\)"
    r"(?:\n[ \t]*print\([^\n]*TIME_ANCHOR[^\n]*\))?")

def _call_fix(m):
    ind = m.group(1)
    return (ind + '_ok = save_to_github(TIME_ANCHOR_FILE, anchor)\n'
            + ind + 'print("TIME_ANCHOR SAVED" if _ok else "TIME_ANCHOR FAILED")')

def main():
    try:
        with io.open(SRC_FILE, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        print("PATCH ERROR cannot read %s: %s" % (SRC_FILE, e))
        sys.exit(1)
    if MARKER in src:
        print("PATCH already applied — skip")
        return
    src2, n_func = FUNC_RE.subn(lambda m: NEW_FUNC, src, count=1)
    if n_func != 1:
        print("PATCH_MISSED: save_to_github boundary not found — repo file left untouched")
        return
    src3, n_call = CALL_RE.subn(_call_fix, src2, count=1)
    with io.open(SRC_FILE, "w", encoding="utf-8") as f:
        f.write(src3)
    print("PATCH APPLIED v2.0: save_to_github fully replaced | call-site:",
          "patched" if n_call == 1 else "not found (non-fatal; function logs loudly)")
    sys.exit(0)

if __name__ == "__main__":
    main()
