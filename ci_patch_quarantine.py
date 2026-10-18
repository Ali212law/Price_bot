#!/usr/bin/env python3
# ci_patch_quarantine.py — v1.0 | 2026-10-18 | AI سوم (هوشا)
# Fixed Regex by AI1 (try_open\( instead of try_open$)
import re, sys, io

SRC_FILE = "shadow_lab.py"
MARKER = "QUARANTINED (ci_patch_quarantine v1.0"
FAIL_MARKER_FILE = "quarantine_patch_fail.marker"
DECISION = "D-2026-10-18-02"

# اصلاح شد: اضافه کردن پرانتز برای تطابق با try_open("H6_ATR_STOP", ...)
OPEN_RE = re.compile(
    r'^([ \t]*)try_open\(\s*["\']H6_ATR_STOP["\'][^\n]*\)',
    re.MULTILINE)

def main():
    try:
        with io.open(SRC_FILE, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        print("QUAR PATCH ERROR cannot read %s: %s" % (SRC_FILE, e))
        sys.exit(1)
    if MARKER in src:
        print("QUAR PATCH already applied — skip")
        sys.exit(0)

    def _fix(m):
        ind = m.group(1)
        line1 = (ind + "# QUARANTINED (ci_patch_quarantine v1.0 | %s): "
                 "H6 new entries stopped; open trade still managed to exit; "
                 "data preserved." % DECISION)
        line2 = (ind + 'print("QUAR SKIP: H6_ATR_STOP new entry suppressed '
                 '(%s)")' % DECISION)
        return line1 + "\n" + line2

    src2, n = OPEN_RE.subn(_fix, src)
    if n < 1:
        print("QUAR_PATCH_MISSED: no try_open(H6_ATR_STOP...) found — "
              "repo file left untouched; decision %s NOT enforced" % DECISION)
        try:
            with open(FAIL_MARKER_FILE, "a", encoding="utf-8") as mf:
                mf.write("%s\ttry_open H6_ATR_STOP pattern not found\n" % DECISION)
        except Exception:
            pass
        sys.exit(0)
    with io.open(SRC_FILE, "w", encoding="utf-8") as f:
        f.write(src2)
    print("QUAR PATCH APPLIED: %d try_open(H6) call(s) neutralized — %s"
          % (n, DECISION))
    sys.exit(0)

if __name__ == "__main__":
    main()
