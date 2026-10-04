#!/data/data/com.termux/files/usr/bin/bash
# sync.sh — همگام‌سازی سریع با GitHub
# نسخه: 1.0 (2026-10-04)

G='\033[0;32m'
R='\033[0;31m'
Y='\033[1;33m'
N='\033[0m'

REPO_DIR="$HOME/Price_bot"
cd "$REPO_DIR" 2>/dev/null || {
    echo -e "${R}✗ پوشه پیدا نشد${N}"
    exit 1
}

echo -e "${Y}🔄 syncing...${N}"

OUT=$(git pull 2>&1)
STATUS=$?

if [ $STATUS -eq 0 ]; then
    if echo "$OUT" | grep -q "Already up to date"; then
        echo -e "${G}✓ Already up to date${N}"
    else
        echo -e "${G}✓ Updated${N}"
        echo "$OUT" | grep -E "files? changed|insertion|deletion" | head -5
    fi
else
    echo -e "${R}✗ خطا:${N}"
    echo "$OUT"
fi
