#!/data/data/com.termux/files/usr/bin/bash
G='\033[0;32m'
R='\033[0;31m'
Y='\033[1;33m'
B='\033[0;34m'
C='\033[0;36m'
M='\033[0;35m'
W='\033[1;37m'
N='\033[0m'
REPO_DIR="$HOME/Price_bot"
cd "$REPO_DIR" 2>/dev/null || { echo -e "${R}✗ پوشه پیدا نشد${N}"; exit 1; }
clear
echo ""
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo -e "${C}  🤖 BTC TRADE BOT — $(date '+%Y-%m-%d %H:%M:%S')${N}"
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo ""
echo -e "${Y}🔄 در حال همگام‌سازی با GitHub...${N}"
SYNC_OUTPUT=$(git pull 2>&1)
if echo "$SYNC_OUTPUT" | grep -q "Already up to date"; then
    echo -e "${G}✓ از قبل همگام بود${N}"
else
    echo -e "${G}✓ همگام شد${N}"
fi
echo ""
echo -e "${M}📜 ۳ commit آخر:${N}"
echo -e "${B}────────────────────────────────────────────────────────────${N}"
git log --oneline -3 --pretty=format:'%h|%s|%ar' 2>/dev/null | while IFS='|' read -r hash msg when; do
    printf "  ${W}%s${N}  %-40s  ${Y}(%s)${N}\n" "$hash" "$msg" "$when"
done
echo ""
echo -e "${B}────────────────────────────────────────────────────────────${N}"
echo ""
echo -e "${Y}📊 Paper & Shadow:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('paper_trades.json') as f: paper = json.load(f)
    p_open = sum(1 for t in paper if t.get('status') == 'open')
    p_closed = sum(1 for t in paper if t.get('status') == 'closed')
    p_wins = sum(1 for t in paper if t.get('status')=='closed' and (t.get('net_pnl') or t.get('profit_net_toman') or 0) > 0)
    p_net = sum((t.get('net_pnl') or t.get('profit_net_toman') or 0) for t in paper if t.get('status')=='closed')
    p_wr = (p_wins / p_closed * 100) if p_closed else 0
    c = '\033[0;32m' if p_net >= 0 else '\033[0;31m'
    print(f"  📄 Paper:  total={len(paper)} | open={p_open} | closed={p_closed} | WR={p_wr:.0f}% | net={c}{p_net:+,.0f}\033[0m")
    with open('shadow_trades.json') as f: shadow = json.load(f)
    s_open = sum(1 for t in shadow if t.get('status') == 'open')
    s_closed = sum(1 for t in shadow if t.get('status') == 'closed')
    s_wins = sum(1 for t in shadow if t.get('status')=='closed' and (t.get('net_pnl') or t.get('profit_net_toman') or 0) > 0)
    s_net = sum((t.get('net_pnl') or t.get('profit_net_toman') or 0) for t in shadow if t.get('status')=='closed')
    s_wr = (s_wins / s_closed * 100) if s_closed else 0
    c = '\033[0;32m' if s_net >= 0 else '\033[0;31m'
    print(f"  👻 Shadow: total={len(shadow)} | open={s_open} | closed={s_closed} | WR={s_wr:.0f}% | net={c}{s_net:+,.0f}\033[0m")
except Exception as e: print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF
echo ""
echo -e "${Y}💹 قیمت لحظه‌ای BTC/TMN:${N}"
PRICE=$(python3 -c "
import requests
try:
    r = requests.get('https://api.wallex.ir/v1/markets', timeout=10)
    btc = r.json()['result']['symbols']['BTCTMN']['stats']
    print(f\"{float(btc['lastPrice'])/1e9:.3f}|{float(btc['bidPrice'])/1e9:.3f}|{float(btc['askPrice'])/1e9:.3f}\")
except: print('ERROR')
" 2>/dev/null)
if [ "$PRICE" != "ERROR" ] && [ -n "$PRICE" ]; then
    LAST=$(echo $PRICE | cut -d'|' -f1)
    BID=$(echo $PRICE | cut -d'|' -f2)
    ASK=$(echo $PRICE | cut -d'|' -f3)
    echo -e "  ${W}last:${N} ${G}${LAST}B${N}  |  ${W}bid:${N} ${BID}B  |  ${W}ask:${N} ${ASK}B"
else
    echo -e "  ${R}✗ خطا${N}"
fi
echo ""
echo -e "${Y}📰 اخبار ایران:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('iran_news_data.json') as f: data = json.load(f)
    impact = data.get('stats', {}).get('by_btc_impact', {})
    up, down = impact.get('up', 0), impact.get('down', 0)
    total = data.get('stats', {}).get('recent_news_24h', 0)
    if up > down * 2 and up >= 3: sent = '\033[0;32mbullish ⬆\033[0m'
    elif down > up * 2 and down >= 3: sent = '\033[0;31mbearish ⬇\033[0m'
    else: sent = '\033[1;33mneutral ➡\033[0m'
    print(f"  اخبار 24h: {total} | up={up} down={down} | sentiment: {sent}")
except Exception as e: print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF
echo ""
echo -e "${Y}🌍 اخبار جهانی:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('news_history.json') as f: news = json.load(f)
    if news:
        l = news[-1]
        pos, neg = l.get('pos', 0), l.get('neg', 0)
        if pos > neg * 2: status = '\033[0;32mBULLISH (veto SELL)\033[0m'
        elif neg > pos * 2: status = '\033[0;31mBEARISH (veto BUY)\033[0m'
        else: status = '\033[1;33mNEUTRAL\033[0m'
        print(f"  sentiment={l.get('sentiment','?')} | pos={pos} neg={neg}")
        print(f"  veto_status: {status}")
except Exception as e: print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF
echo ""
echo -e "${Y}📈 BTC History:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    with open('btc_history.json') as f: btc = json.load(f)
    print(f"  records: {len(btc)}")
    if btc:
        print(f"  oldest: {btc[0][0][:16]}  ({btc[0][1]/1e9:.2f}B)")
        print(f"  latest: {btc[-1][0][:16]}  ({btc[-1][1]/1e9:.2f}B)")
except Exception as e: print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF
echo ""
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo -e "${C}  ${G}✓ پایان${N}  |  ${W}$(date '+%H:%M:%S')${N}"
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo ""
