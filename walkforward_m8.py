#!/usr/bin/env python3
# walkforward_m8.py — Walk-Forward 4-window for locked matrix M8 (Adapted by AI1)
import json
import os

MATRIX = {"SOL": "DIP", "ETH": "DIP", "XRP": "BREAKOUT", "BTC": "BREAKOUT"}
SL_PCT = 0.02
TP_PCT = 0.04
COST_PCT = 0.002
RISK_PCT = 0.005
EQUITY_START = 1000000.0
N_WINDOWS = 4
WARMUP = 50
RSI_PERIOD = 14
BREAKOUT_LOOKBACK = 20
MAX_HOLD = 50

def compute_rsi(closes, period=14):
    n = len(closes)
    rsi = [None] * n
    if n <= period: return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        chg = closes[i] - closes[i-1]
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rsi[period] = 100.0 if avg_l == 0 else 100 - (100 / (1 + (avg_g / avg_l)))
    for i in range(period + 1, n):
        chg = closes[i] - closes[i-1]
        avg_g = (avg_g * (period - 1) + max(chg, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-chg, 0)) / period
        rsi[i] = 100.0 if avg_l == 0 else 100 - (100 / (1 + (avg_g / avg_l)))
    return rsi

def is_breakout(candles, idx, lookback=20):
    if idx < lookback: return False
    cur_close = candles[idx]["close"]
    prev_high = max(c["high"] for c in candles[idx-lookback:idx])
    return cur_close > prev_high

def backtest_window(candles, signal_type, equity_start, symbol):
    closes = [c["close"] for c in candles]
    rsi_list = compute_rsi(closes, RSI_PERIOD)
    equity = equity_start
    equity_peak = equity_start
    max_dd = 0.0
    trades = []
    gross_profit = 0.0
    gross_loss = 0.0
    i = WARMUP
    n = len(candles)
    open_pos = None

    def update_dd(eq):
        nonlocal equity_peak, max_dd
        if eq > equity_peak: equity_peak = eq
        if equity_peak > 0:
            dd = (equity_peak - eq) / equity_peak
            if dd > max_dd: max_dd = dd

    while i < n:
        if open_pos is None:
            signal = False
            if signal_type == "DIP" and rsi_list[i] is not None and rsi_list[i] < 30: signal = True
            elif signal_type == "BREAKOUT" and is_breakout(candles, i, BREAKOUT_LOOKBACK): signal = True
            
            if signal:
                entry = candles[i]["close"]
                risk_amount = equity * RISK_PCT
                
                if symbol == "BTC" and i >= 14:
                    trs = [max(candles[k]["high"] - candles[k]["low"], abs(candles[k]["high"] - candles[k-1]["close"]), abs(candles[k]["low"] - candles[k-1]["close"])) for k in range(i-13, i+1)]
                    sl_pct = max(0.01, min(0.05, (sum(trs)/14 * 2.0 / entry)))
                else:
                    sl_pct = SL_PCT
                    
                tp_pct = sl_pct * 2 if symbol == "BTC" else TP_PCT
                denom = sl_pct + COST_PCT
                size = risk_amount / denom if denom > 0 else 0
                open_pos = {"entry_idx": i, "entry_price": entry, "sl": entry*(1-sl_pct), "tp": entry*(1+tp_pct), "size": size, "risk_amount": risk_amount}
        else:
            c = candles[i]
            exit_price, exit_reason = None, None
            if c["low"] <= open_pos["sl"]: exit_price, exit_reason = open_pos["sl"], "SL"
            elif c["high"] >= open_pos["tp"]: exit_price, exit_reason = open_pos["tp"], "TP"
            elif (i - open_pos["entry_idx"]) >= MAX_HOLD: exit_price, exit_reason = c["close"], "TIME"
                
            if exit_price is not None:
                gross = (exit_price - open_pos["entry_price"]) / open_pos["entry_price"] * open_pos["size"]
                net = gross - (open_pos["size"] * COST_PCT)
                equity += net
                update_dd(equity)
                if net > 0: gross_profit += net
                else: gross_loss += abs(net)
                trades.append({"net": net})
                open_pos = None
        i += 1

    if open_pos is not None:
        gross = (candles[-1]["close"] - open_pos["entry_price"]) / open_pos["entry_price"] * open_pos["size"]
        net = gross - (open_pos["size"] * COST_PCT)
        equity += net
        update_dd(equity)
        if net > 0: gross_profit += net
        else: gross_loss += abs(net)
        trades.append({"net": net})

    wins = sum(1 for t in trades if t["net"] > 0)
    wr = (wins / len(trades) * 100) if trades else 0.0
    net_total = sum(t["net"] for t in trades)
    net_pct = (net_total / equity_start * 100) if equity_start else 0.0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    return {"n": len(trades), "wr": round(wr, 2), "net_pct": round(net_pct, 3), "pf": round(pf, 3), "max_dd_pct": round(max_dd * 100, 3)}

def main():
    if not os.path.exists("global_history.json"):
        print("MISSING FILE: global_history.json")
        return
        
    with open("global_history.json", encoding="utf-8") as f:
        raw_data = json.load(f)

    all_candles = {}
    for sym in MATRIX.keys():
        if sym + "USDT" not in raw_data: continue
        all_candles[sym] = [{"time": c["t"], "open": c["o"], "high": c["h"], "low": c["l"], "close": c["c"]} for c in raw_data[sym + "USDT"]]

    results = {}
    for sym, sig in MATRIX.items():
        if sym not in all_candles: continue
        candles = all_candles[sym]
        wsize = len(candles) // N_WINDOWS
        sym_res = []
        print(f"\n== {sym} as {sig} ==")
        for w in range(N_WINDOWS):
            window = candles[w*wsize : (w+1)*wsize if w < N_WINDOWS-1 else len(candles)]
            r = backtest_window(window, sig, EQUITY_START, sym)
            sym_res.append(r)
            print(f"W{w+1} n={r['n']} WR={r['wr']}% Net%={r['net_pct']}% PF={r['pf']} MaxDD={r['max_dd_pct']}%")
            
        pos = sum(1 for r in sym_res if r["net_pct"] > 0)
        results[sym] = {"signal": sig, "windows": sym_res, "positive_windows": pos}

    with open("walkforward_results.json", "w", encoding="utf-8") as out:
        json.dump(results, out, ensure_ascii=False, indent=2)
    print("\nSaved: walkforward_results.json")

if __name__ == "__main__":
    main()
