import json
import sys

def net(t):
    for k in ("net_pnl", "profit_net_toman"):
        v = t.get(k)
        if v is not None: return float(v)
    return 0.0

def summarize(name, trades):
    closed = [t for t in trades if t.get('status')=='closed']
    opens  = [t for t in trades if t.get('status')=='open']
    nets = [net(t) for t in closed]
    wins = sum(1 for n in nets if n > 0)
    wr = (wins/len(closed)*100) if closed else 0
    return {
        'name': name, 'total': len(trades), 'closed': len(closed),
        'open': len(opens), 'wr': wr, 'net': sum(nets),
    }

shadow = json.load(open('shadow_trades.json'))
paper  = json.load(open('paper_trades.json'))

# تفکیک دقیق
top_all  = [t for t in shadow if t.get('shadow_type')=='top_only']
top_tf   = [t for t in shadow if t.get('shadow_type')=='top_trend_filtered']
rej_buy  = [t for t in shadow if t.get('shadow_type')=='rejected_already_open_buy']
rej_sell = [t for t in shadow if t.get('shadow_type')=='rejected_already_open_sell']
veto     = [t for t in shadow if t.get('shadow_type')=='veto']

p_all    = paper
p_closed = [t for t in paper if t.get('status')=='closed']
p_nets   = [net(t) for t in p_closed]
p_wins   = sum(1 for n in p_nets if n > 0)

print("=" * 65)
print("📊 SHADOW — تفکیک تمیز")
print("=" * 65)
print(f"{'group':<32} {'total':>5} {'closed':>6} {'open':>5} {'WR':>6} {'net':>10}")
print("-" * 65)

groups = [
    ('top_only', top_all),
    ('top_trend_filtered', top_tf),
    ('rejected_already_open_buy', rej_buy),
    ('rejected_already_open_sell', rej_sell),
    ('veto', veto),
]

grand_net = 0
grand_closed = 0
for name, ts in groups:
    s = summarize(name, ts)
    if s['closed'] > 0:
        print(f"{name:<32} {s['total']:>5} {s['closed']:>6} {s['open']:>5} "
              f"{s['wr']:>5.1f}% {s['net']:>+10,.0f}")
        grand_net += s['net']
        grand_closed += s['closed']
    elif s['total'] > 0:
        print(f"{name:<32} {s['total']:>5} {s['closed']:>6} {s['open']:>5} "
              f"{'-':>6} {'-':>10}")

print("-" * 65)
print(f"{'SHADOW TOTAL (closed)':<32} {'':>5} {grand_closed:>6} {'':>5} "
      f"{'':>6} {grand_net:>+10,.0f}")

print()
print("=" * 65)
print("📄 PAPER")
print("=" * 65)
print(f"{'Paper total':<32} {len(p_all):>5}")
print(f"{'Paper closed':<32} {len(p_closed):>5}")
wr_p = (p_wins/len(p_closed)*100) if p_closed else 0
print(f"{'Paper WR':<32} {wr_p:>5.1f}%")
print(f"{'Paper net':<32} {'':>5} {sum(p_nets):>+10,.0f}")
