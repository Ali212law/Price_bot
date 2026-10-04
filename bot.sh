#!/data/data/com.termux/files/usr/bin/bash
# bot.sh — دستور جادویی BTC Trade Bot
# نسخه: 2.0 (2026-10-04)

# رنگ‌ها
G='\033[0;32m'   # سبز
R='\033[0;31m'   # قرمز
Y='\033[1;33m'   # زرد
B='\033[0;34m'   # آبی
C='\033[0;36m'   # فیروزه‌ای
M='\033[0;35m'   # بنفش
W='\033[1;37m'   # سفید
N='\033[0m'      # بدون رنگ

REPO_DIR="$HOME/Price_bot"

# اگه توی ریپو نیستیم، برو
cd "$REPO_DIR" 2>/dev/null || {
    echo -e "${R}✗ پوشه $REPO_DIR پیدا نشد${N}"
    exit 1
}

clear

echo ""
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo -e "${C}  🤖 BTC TRADE BOT — $(date '+%Y-%m-%d %H:%M:%S')${N}"
echo -e "${C}════════════════════════════════════════════════════════════${N}"

# ═══════════════════════════════════════════════
# ۱) همگام‌سازی با GitHub
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}🔄 در حال همگام‌سازی با GitHub...${N}"

SYNC_OUTPUT=$(git pull 2>&1)
SYNC_STATUS=$?

if [ $SYNC_STATUS -eq 0 ]; then
    if echo "$SYNC_OUTPUT" | grep -q "Already up to date"; then
        echo -e "${G}✓ از قبل همگام بود${N}"
    elif echo "$SYNC_OUTPUT" | grep -q "Fast-forward\|files changed"; then
        FILES_CHANGED=$(echo "$SYNC_OUTPUT" | grep -oE "[0-9]+ files? changed" | head -1)
        echo -e "${G}✓ همگام شد${N}  ${W}($FILES_CHANGED)${N}"
    else
        echo -e "${G}✓ همگام شد${N}"
    fi
else
    echo -e "${R}✗ خطا در همگام‌سازی${N}"
    echo -e "${R}  $SYNC_OUTPUT${N}"
fi

# ═══════════════════════════════════════════════
# ۲) سه commit آخر
# ═══════════════════════════════════════════════
echo ""
echo -e "${M}📜 ۳ commit آخر:${N}"
echo -e "${B}────────────────────────────────────────────────────────────${N}"
git log --oneline -3 --pretty=format:"  ${W}%h${N}  %s  ${Y}(%ar)${N}" 2>/dev/null | sed 's/^/ /'
echo ""
echo -e "${B}────────────────────────────────────────────────────────────${N}"

# ═══════════════════════════════════════════════
# ۳) وضعیت Paper / Shadow
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}📊 Paper & Shadow:${N}"

python3 << 'PYEOF' 2>/dev/null
import json
try:
    # Paper
    with open('paper_trades.json') as f:
        paper = json.load(f)
    p_open = sum(1 for t in paper if t.get('status') == 'open')
    p_closed = sum(1 for t in paper if t.get('status') == 'closed')
    p_wins = 0
    p_net = 0
    for t in paper:
        if t.get('status') == 'closed':
            net = t.get('net_pnl') or t.get('profit_net_toman') or 0
            p_net += net
            if net > 0: p_wins += 1
    p_wr = (p_wins / p_closed * 100) if p_closed else 0
    color = '\033[0;32m' if p_net >= 0 else '\033[0;31m'
    print(f"  📄 Paper:  total={len(paper)} | open={p_open} | closed={p_closed} | WR={p_wr:.0f}% | net={color}{p_net:+,.0f}\033[0m")

    # Shadow
    with open('shadow_trades.json') as f:
        shadow = json.load(f)
    s_open = sum(1 for t in shadow if t.get('status') == 'open')
    s_closed = sum(1 for t in shadow if t.get('status') == 'closed')
    s_wins = 0
    s_net = 0
    for t in shadow:
        if t.get('status') == 'closed':
            net = t.get('net_pnl') or t.get('profit_net_toman') or 0
            s_net += net
            if net > 0: s_wins += 1
    s_wr = (s_wins / s_closed * 100) if s_closed else 0
    color = '\033[0;32m' if s_net >= 0 else '\033[0;31m'
    print(f"  👻 Shadow: total={len(shadow)} | open={s_open} | closed={s_closed} | WR={s_wr:.0f}% | net={color}{s_net:+,.0f}\033[0m")

except Exception as e:
    print(f"  \033[0;31m✗ خطا در خواندن داده: {e}\033[0m")
PYEOF

# ═══════════════════════════════════════════════
# ۴) قیمت لحظه‌ای BTC/TMN
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}💹 قیمت لحظه‌ای BTC/TMN از والکس:${N}"

PRICE=$(python3 -c "
import requests
try:
    r = requests.get('https://api.wallex.ir/v1/markets', timeout=10)
    d = r.json()
    btc = d['result']['symbols']['BTCTMN']['stats']
    last = float(btc['lastPrice'])
    bid = float(btc['bidPrice'])
    ask = float(btc['askPrice'])
    print(f'{last/1e9:.3f}|{bid/1e9:.3f}|{ask/1e9:.3f}')
except Exception as e:
    print('ERROR')
" 2>/dev/null)

if [ "$PRICE" != "ERROR" ] && [ -n "$PRICE" ]; then
    LAST=$(echo $PRICE | cut -d'|' -f1)
    BID=$(echo $PRICE | cut -d'|' -f2)
    ASK=$(echo $PRICE | cut -d'|' -f3)
    echo -e "  ${W}last:${N} ${G}${LAST}B${N}  |  ${W}bid:${N} ${LAST}B  |  ${W}ask:${N} ${LAST}B"
else
    echo -e "  ${R}✗ خطا در دریافت قیمت${N}"
fi

# ═══════════════════════════════════════════════
# ۵) اخبار ایران
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}📰 اخبار ایران:${N}"

python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('iran_news_data.json') as f:
        data = json.load(f)
    stats = data.get('stats', {})
    impact = stats.get('by_btc_impact', {})
    up = impact.get('up', 0)
    down = impact.get('down', 0)
    total = stats.get('recent_news_24h', 0)

    if up > down * 2 and up >= 3:
        sent = '\033[0;32mbullish ⬆️\033[0m'
    elif down > up * 2 and down >= 3:
        sent = '\033[0;31mbearish ⬇️\033[0m'
    else:
        sent = '\033[1;33mneutral ➡️\033[0m'

    print(f"  اخبار 24h: {total} | up={up} down={down} | sentiment: {sent}")
except Exception as e:
    print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF

# ═══════════════════════════════════════════════
# ۶) اخبار جهانی (آخرین snapshot)
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}🌍 اخبار جهانی (آخرین snapshot):${N}"

python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('news_history.json') as f:
        news = json.load(f)
    if news:
        latest = news[-1]
        pos = latest.get('pos', 0)
        neg = latest.get('neg', 0)
        sent = latest.get('sentiment', '?')

        if pos > neg * 2:
            status = 'BULLISH (veto SELL)'
        elif neg > pos * 2:
            status = 'BEARISH (veto BUY)'
        else:
            status = 'NEUTRAL'

        color = '\033[0;32m' if 'BULLISH' in status else ('\033[0;31m' if 'BEARISH' in status else '\033[1;33m')
        print(f"  sentiment={sent} | pos={pos} neg={neg}")
        print(f"  veto_status: {color}{status}\033[0m")
except Exception as e:
    print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF

# ═══════════════════════════════════════════════
# ۷) آخرین BTC History
# ═══════════════════════════════════════════════
echo ""
echo -e "${Y}📈 BTC History:${N}"

python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('btc_history.json') as f:
        btc = json.load(f)
    print(f"  records: {len(btc)}")
    if btc:
        first_t = btc[0][0][:16]
        last_t = btc[-1][0][:16]
        first_p = btc[0][1] / 1e9
        last_p = btc[-1][1] / 1e9
        print(f"  oldest: {first_t}  ({first_p:.2f}B)")
        print(f"  latest: {last_t}  ({last_p:.2f}B)")
except Exception as e:
    print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF

# ═══════════════════════════════════════════════
# پایان
# ═══════════════════════════════════════════════
echo ""
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo -e "${C}  ${G}✓ پایان${N}  |  ${W}$(date '+%H:%M:%S')${N}${C}${N}"
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo ""
