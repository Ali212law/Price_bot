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
OUT=$(git pull 2>&1)
if echo "$OUT" | grep -q "Already up to date"; then
    echo -e "${G}✓ از قبل همگام بود${N}"
else
    echo -e "${G}✓ همگام شد${N}"
fi

echo ""
echo -e "${M}📜 ۳ commit آخر:${N}"
echo -e "${B}────────────────────────────────────────────────────────────${N}"
git log --oneline -3 --pretty=format:'%h|%s|%ar' 2>/dev/null | while IFS='|' read -r h m w; do
    printf "  ${W}%s${N}  %-40s  ${Y}(%s)${N}\n" "$h" "$m" "$w"
done
echo ""
echo -e "${B}────────────────────────────────────────────────────────────${N}"

echo ""
echo -e "${Y}📊 Paper & Shadow:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    paper = json.load(open('paper_trades.json'))
    po = sum(1 for t in paper if t.get('status')=='open')
    pc = sum(1 for t in paper if t.get('status')=='closed')
    pw = sum(1 for t in paper if t.get('status')=='closed' and (t.get('net_pnl') or t.get('profit_net_toman') or 0) > 0)
    pn = sum((t.get('net_pnl') or t.get('profit_net_toman') or 0) for t in paper if t.get('status')=='closed')
    pwr = (pw/pc*100) if pc else 0
    c = '\033[0;32m' if pn >= 0 else '\033[0;31m'
    print(f"  📄 Paper:  total={len(paper)} | open={po} | closed={pc} | WR={pwr:.0f}% | net={c}{pn:+,.0f}\033[0m")
    shadow = json.load(open('shadow_trades.json'))
    so = sum(1 for t in shadow if t.get('status')=='open')
    sc = sum(1 for t in shadow if t.get('status')=='closed')
    sw = sum(1 for t in shadow if t.get('status')=='closed' and (t.get('net_pnl') or t.get('profit_net_toman') or 0) > 0)
    sn = sum((t.get('net_pnl') or t.get('profit_net_toman') or 0) for t in shadow if t.get('status')=='closed')
    swr = (sw/sc*100) if sc else 0
    c = '\033[0;32m' if sn >= 0 else '\033[0;31m'
    print(f"  👻 Shadow: total={len(shadow)} | open={so} | closed={sc} | WR={swr:.0f}% | net={c}{sn:+,.0f}\033[0m")
except Exception as e:
    print(f"  \033[0;31m✗ خطا: {e}\033[0m")
PYEOF

echo ""
echo -e "${Y}💹 قیمت لحظه‌ای BTC/TMN:${N}"
PRICE=$(python3 -c "
import requests
try:
    r = requests.get('https://api.wallex.ir/v1/markets', timeout=10)
    b = r.json()['result']['symbols']['BTCTMN']['stats']
    print(f\"{float(b['lastPrice'])/1e9:.3f}|{float(b['bidPrice'])/1e9:.3f}|{float(b['askPrice'])/1e9:.3f}\")
except: print('ERROR')
" 2>/dev/null)
if [ "$PRICE" != "ERROR" ] && [ -n "$PRICE" ]; then
    L=$(echo $PRICE|cut -d'|' -f1); BID=$(echo $PRICE|cut -d'|' -f2); A=$(echo $PRICE|cut -d'|' -f3)
    echo -e "  ${W}last:${N} ${G}${L}B${N}  |  ${W}bid:${N} ${BID}B  |  ${W}ask:${N} ${A}B"
else
    echo -e "  ${R}✗ خطا${N}"
fi

echo ""
echo -e "${Y}📰 اخبار ایران:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    d = json.load(open('iran_news_data.json'))
    i = d.get('stats',{}).get('by_btc_impact',{})
    u,dn = i.get('up',0),i.get('down',0)
    t = d.get('stats',{}).get('recent_news_24h',0)
    if u>dn*2 and u>=3: s='\033[0;32mbullish ⬆\033[0m'
    elif dn>u*2 and dn>=3: s='\033[0;31mbearish ⬇\033[0m'
    else: s='\033[1;33mneutral ➡\033[0m'
    print(f"  اخبار 24h: {t} | up={u} down={dn} | sentiment: {s}")
except Exception as e: print(f"  \033[0;31m✗ {e}\033[0m")
PYEOF

echo ""
echo -e "${Y}🌍 اخبار جهانی:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    n = json.load(open('news_history.json'))
    if n:
        l=n[-1]; p,ng=l.get('pos',0),l.get('neg',0)
        if p>ng*2: st='\033[0;32mBULLISH (veto SELL)\033[0m'
        elif ng>p*2: st='\033[0;31mBEARISH (veto BUY)\033[0m'
        else: st='\033[1;33mNEUTRAL\033[0m'
        print(f"  sentiment={l.get('sentiment','?')} | pos={p} neg={ng}")
        print(f"  veto_status: {st}")
except Exception as e: print(f"  \033[0;31m✗ {e}\033[0m")
PYEOF

echo ""
echo -e "${Y}📈 BTC History:${N}"
python3 << 'PYEOF' 2>/dev/null
import json
try:
    b = json.load(open('btc_history.json'))
    print(f"  records: {len(b)}")
    if b:
        print(f"  oldest: {b[0][0][:16]}  ({b[0][1]/1e9:.2f}B)")
        print(f"  latest: {b[-1][0][:16]}  ({b[-1][1]/1e9:.2f}B)")
except Exception as e: print(f"  \033[0;31m✗ {e}\033[0m")
PYEOF

echo ""
echo -e "${Y}📡 وضعیت Live و ریسک اینترنت:${N}"
echo -e "${B}────────────────────────────────────────────────────────────${N}"
echo -e "  Mode: ${G}🔵 Paper Trading${N}  ${W}(Live غیرفعال)${N}"
echo ""
echo -e "  ${W}آمادگی Live:${N}"
echo -e "    ${R}❌${N} SL سمت سرور والکس"
echo -e "    ${R}❌${N} VPS ایرانی"
echo -e "    ${R}❌${N} Manual Emergency Exit"
echo -e "    ${Y}⏳${N} ۶ ماه Paper سودآور"
echo ""
echo -e "  ${W}در صورت قطعی اینترنت:${N}"
echo -e "    ${G}🟢${N} موبایل قطع        → ربات GitHub کار می‌کند"
echo -e "    ${Y}🟡${N} بین‌الملل قطع      → ربات متوقف، پوزیشن معلق"
echo -e "    ${R}🔴${N} قطعی کامل         → تعطیلی موقت"
echo ""
echo -e "  ${W}راهنمای کامل:${N} ${C}SAFETY.md${N}"
echo -e "${B}────────────────────────────────────────────────────────────${N}"

echo ""
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo -e "${C}  ${G}✓ پایان${N}  |  ${W}$(date '+%H:%M:%S')${N}"
echo -e "${C}════════════════════════════════════════════════════════════${N}"
echo ""
