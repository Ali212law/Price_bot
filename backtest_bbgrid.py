#!/usr/bin/env python3
# backtest_bbgrid.py — BBGRID: Bollinger-Triggered Grid (FINAL Grid Attempt)

import requests, time

SYMBOLS = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT"]
INTERVAL = "15m"
FETCH_DAYS = 730
MAKER_FEE = 0.0002
SLIPPAGE = 0.001
TOTAL_FEE = MAKER_FEE + SLIPPAGE

CAPITAL_PER_ASSET = 1000.0
POSITION_PCT = 0.08
CAP_PER_LEVEL = CAPITAL_PER_ASSET * POSITION_PCT

ATR_MULT = 1.5
NUM_LEVELS = 3
ADX_MAX = 30.0
RSI_MAX = 30.0
BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14

CANCEL_UNFILLED_HOURS = 24
CLOSE_FILLED_HOURS = 48

def fetch_klines(symbol, interval, days):
    all_candles = []
    end_time = int(time.time() * 1000)
    target = days * 24 * (4 if interval == "15m" else 12)
    while len(all_candles) < target:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&endTime={end_time}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data: break
                for k in data:
                    all_candles.append({
                        "t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                        "l": float(k[3]), "c": float(k[4])
                    })
                end_time = data[0][0] - 1
            else:
                break
        except:
            break
        time.sleep(0.05)
    unique = {c['t']: c for c in all_candles}
    return sorted(list(unique.values()), key=lambda x: x['t'])

def calc_indicators(candles):
    n = len(candles)
    closes = [c['c'] for c in candles]
    
    lower_bb = [0.0] * n
    for i in range(BB_PERIOD - 1, n):
        window = closes[i - BB_PERIOD + 1 : i + 1]
        sma = sum(window) / BB_PERIOD
        variance = sum((x - sma) ** 2 for x in window) / BB_PERIOD
        std = variance ** 0.5
        lower_bb[i] = sma - BB_STD * std
    
    rsi = [50.0] * n
    if n > RSI_PERIOD:
        gains, losses = [], []
        for i in range(1, RSI_PERIOD + 1):
            chg = closes[i] - closes[i-1]
            gains.append(max(chg, 0)); losses.append(max(-chg, 0))
        ag = sum(gains) / RSI_PERIOD
        al = sum(losses) / RSI_PERIOD
        rsi[RSI_PERIOD] = 100 - (100 / (1 + ag/al)) if al > 0 else 100
        for i in range(RSI_PERIOD + 1, n):
            chg = closes[i] - closes[i-1]
            gain = max(chg, 0); loss = max(-chg, 0)
            ag = (ag * (RSI_PERIOD - 1) + gain) / RSI_PERIOD
            al = (al * (RSI_PERIOD - 1) + loss) / RSI_PERIOD
            rsi[i] = 100 - (100 / (1 + ag/al)) if al > 0 else 100
    
    atr = [0.0] * n
    if n > ATR_PERIOD:
        trs = []
        for i in range(1, n):
            tr = max(candles[i]['h'] - candles[i]['l'], abs(candles[i]['h'] - candles[i-1]['c']), abs(candles[i]['l'] - candles[i-1]['c']))
            trs.append(tr)
            if i >= ATR_PERIOD:
                atr[i] = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD
    
    adx = [0.0] * n
    if n > ADX_PERIOD * 2:
        tr_list, plus_dm, minus_dm = [], [], []
        for i in range(1, n):
            h, l, pc = candles[i]['h'], candles[i]['l'], candles[i-1]['c']
            ph, pl = candles[i-1]['h'], candles[i-1]['l']
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
            up = h - ph; down = pl - l
            plus_dm.append(up if (up > down and up > 0) else 0)
            minus_dm.append(down if (down > up and down > 0) else 0)
        smooth_tr = sum(tr_list[:ADX_PERIOD])
        smooth_plus = sum(plus_dm[:ADX_PERIOD])
        smooth_minus = sum(minus_dm[:ADX_PERIOD])
        dx_list = []
        for i in range(ADX_PERIOD, len(tr_list)):
            smooth_tr = smooth_tr - (smooth_tr / ADX_PERIOD) + tr_list[i]
            smooth_plus = smooth_plus - (smooth_plus / ADX_PERIOD) + plus_dm[i]
            smooth_minus = smooth_minus - (smooth_minus / ADX_PERIOD) + minus_dm[i]
            pdi = (smooth_plus / smooth_tr) * 100 if smooth_tr > 0 else 0
            mdi = (smooth_minus / smooth_tr) * 100 if smooth_tr > 0 else 0
            dx = (abs(pdi - mdi) / (pdi + mdi)) * 100 if (pdi + mdi) > 0 else 0
            dx_list.append(dx)
        if len(dx_list) >= ADX_PERIOD:
            adx_val = sum(dx_list[:ADX_PERIOD]) / ADX_PERIOD
            adx[ADX_PERIOD*2-1] = adx_val
            for i in range(ADX_PERIOD, len(dx_list)):
                adx_val = ((adx_val * (ADX_PERIOD - 1)) + dx_list[i]) / ADX_PERIOD
                adx[i + ADX_PERIOD] = adx_val
    
    return lower_bb, rsi, atr, adx

def run_bbgrid(candles, lower_bb, rsi, atr, adx):
    n = len(candles)
    active = False
    cycle_start_time = 0
    levels = []
    cash = CAPITAL_PER_ASSET
    trades = 0
    wins = 0
    losses = 0
    equity_peak = CAPITAL_PER_ASSET
    max_dd = 0.0
    
    for i in range(50, n):
        c = candles[i]
        
        if active:
            for lvl in levels:
                if lvl["status"] == "filled":
                    target = lvl["entry"] + ATR_MULT * atr[i] if atr[i] > 0 else lvl["entry"] * 1.02
                    if c['h'] >= target:
                        proceeds = lvl["qty"] * target * (1 - TOTAL_FEE)
                        cash += proceeds
                        lvl["status"] = "sold"
                        trades += 1
                        wins += 1
            
            filled_levels = [lvl for lvl in levels if lvl["status"] == "filled"]
            if filled_levels:
                lowest_entry = min(lvl["entry"] for lvl in filled_levels)
                stop_price = lowest_entry - 2 * ATR_MULT * atr[i] if atr[i] > 0 else lowest_entry * 0.95
                if c['l'] <= stop_price:
                    for lvl in filled_levels:
                        proceeds = lvl["qty"] * c['c'] * (1 - TOTAL_FEE)
                        cash += proceeds
                        lvl["status"] = "sold"
                        trades += 1
                        losses += 1
            
            for lvl in levels:
                if lvl["status"] == "pending" and c['l'] <= lvl["price"]:
                    cost = CAP_PER_LEVEL * (1 + TOTAL_FEE)
                    if cash >= cost:
                        qty = CAP_PER_LEVEL / lvl["price"]
                        cash -= cost
                        lvl["status"] = "filled"
                        lvl["qty"] = qty
                        lvl["entry"] = lvl["price"]
            
            hours_since_start = (c['t'] - cycle_start_time) / 3600000
            
            if hours_since_start >= CANCEL_UNFILLED_HOURS:
                for lvl in levels:
                    if lvl["status"] == "pending":
                        lvl["status"] = "cancelled"
            
            if hours_since_start >= CLOSE_FILLED_HOURS:
                for lvl in levels:
                    if lvl["status"] == "filled":
                        proceeds = lvl["qty"] * c['c'] * (1 - TOTAL_FEE)
                        cash += proceeds
                        lvl["status"] = "sold"
                        trades += 1
                        if c['c'] > lvl["entry"]: wins += 1
                        else: losses += 1
            
            if all(lvl["status"] in ("sold", "cancelled") for lvl in levels):
                active = False
                levels = []
        
        else:
            if (lower_bb[i] > 0 and c['c'] < lower_bb[i] and rsi[i] < RSI_MAX and adx[i] < ADX_MAX and atr[i] > 0):
                trigger_price = c['c']
                levels = []
                for k in range(1, NUM_LEVELS + 1):
                    levels.append({"price": trigger_price - k * ATR_MULT * atr[i], "status": "pending", "qty": 0, "entry": 0})
                active = True
                cycle_start_time = c['t']
        
        position_value = sum(lvl["qty"] * c['c'] for lvl in levels if lvl["status"] == "filled")
        equity = cash + position_value
        if equity > equity_peak: equity_peak = equity
        dd = (equity_peak - equity) / equity_peak * 100 if equity_peak > 0 else 0
        if dd > max_dd: max_dd = dd
    
    final_price = candles[-1]['c']
    final_position_value = sum(lvl["qty"] * final_price for lvl in levels if lvl["status"] == "filled")
    final_equity = cash + final_position_value
    net_pct = ((final_equity / CAPITAL_PER_ASSET) - 1) * 100
    win_rate = (wins / trades * 100) if trades > 0 else 0
    
    return {"final": final_equity, "net_pct": net_pct, "max_dd": max_dd, "trades": trades, "wins": wins, "losses": losses, "win_rate": win_rate}

def main():
    print("=== BBGRID: FINAL Grid Attempt ===\n")
    
    total_final = 0
    total_initial = 0
    total_trades = 0
    total_wins = 0
    worst_dd = 0
    
    for symbol in SYMBOLS:
        print(f"Fetching {symbol} ({FETCH_DAYS} days)...")
        candles = fetch_klines(symbol, INTERVAL, FETCH_DAYS)
        if len(candles) < 100:
            print(f"  Not enough data\n")
            continue
        print(f"  Got {len(candles)} candles")
        
        lower_bb, rsi, atr, adx = calc_indicators(candles)
        result = run_bbgrid(candles, lower_bb, rsi, atr, adx)
        
        print(f"  Net: {result['net_pct']:+.2f}% | MaxDD: {result['max_dd']:.2f}% | Trades: {result['trades']} | WR: {result['win_rate']:.1f}%\n")
        
        total_final += result['final']
        total_initial += CAPITAL_PER_ASSET
        total_trades += result['trades']
        total_wins += result['wins']
        if result['max_dd'] > worst_dd: worst_dd = result['max_dd']
    
    if total_initial == 0:
        print("No results")
        return
    
    portfolio_net = ((total_final / total_initial) - 1) * 100
    portfolio_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    print("=" * 60)
    print("=== BBGRID Portfolio Results ===")
    print(f"Initial: ${total_initial:,.2f}")
    print(f"Final: ${total_final:,.2f}")
    print(f"Net Return: {portfolio_net:+.2f}%")
    print(f"Worst MaxDD: {worst_dd:.2f}%")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {portfolio_wr:.1f}%")
    ratio = portfolio_net/worst_dd if worst_dd > 0 else 0
    print(f"Return/MaxDD: {ratio:.2f}")
    
    passed = (portfolio_net > 10 and worst_dd < 20 and total_trades > 100 and ratio > 0.5)
    
    print(f"\n{'PASSED' if passed else 'FAILED'}")
    print(f"(Criteria: Net>10%, MaxDD<20%, Trades>100, Return/MaxDD>0.5)")
    
    if not passed:
        print("\nGRID FAMILY PERMANENTLY ARCHIVED. No more attempts.")

if __name__ == "__main__":
    main()
