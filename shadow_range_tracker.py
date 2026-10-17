#!/usr/bin/env python3
"""
shadow_range_tracker.py — Logs DIP/TOP signals that occur in range/chop regimes.
Read-only for production, appends to a separate shadow log.
"""
import requests
import json
import time
from datetime import datetime

def main():
    print("=== SHADOW RANGE TRACKER ===")
    
    # 1. Fetch current price & RSI
    try:
        r = requests.get("https://api.wallex.ir/v1/markets", timeout=10)
        markets = r.json().get('result', {}).get('symbols', {})
        btc = markets.get('BTCTMN', {})
        last_price = float(btc.get('stats', {}).get('lastPrice', 0))
        if last_price > 100_000_000_000: last_price /= 10
    except:
        print("Failed to get price")
        return
        
    # Load btc_history
    try:
        with open('btc_history.json') as f: hist = json.load(f)
    except: hist = []
    
    if len(hist) < 100:
        print("Not enough history")
        return
        
    closes = [p for t, p in hist]
    # Calculate RSI (dummy calc for this example)
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        if ch > 0: gains.append(ch); losses.append(0)
        else: gains.append(0); losses.append(abs(ch))
    ag = sum(gains[-14:]) / 14
    al = sum(losses[-14:]) / 14
    rsi = 100 - (100 / (1 + (ag/al))) if al > 0 else 100
    
    # Calculate chg24h
    chg24h = ((last_price - closes[-96]) / closes[-96]) * 100 if len(closes) >= 96 else 0
    regime = "range" if abs(chg24h) < 0.5 else ("bear" if chg24h < -1.5 else ("bull" if chg24h > 1.5 else "chop"))
    
    print(f"Price: {last_price} | RSI: {rsi:.2f} | chg24h: {chg24h:+.2f}% | regime: {regime}")
    
    if regime in ["range", "chop"]:
        sig = None
        side = None
        if rsi < 30: side, sig = "buy", "DIP"
        elif rsi > 75: side, sig = "sell", "TOP"
        
        if sig:
            print(f"  -> Signal {sig} ({side}) in {regime}. Logging to shadow...")
            # Append to a separate file
            try:
                with open('shadow_range_filtered.json') as f: log = json.load(f)
            except: log = []
            
            log.append({
                "time": datetime.utcnow().isoformat(),
                "signal": sig, "side": side,
                "price": last_price, "rsi": rsi,
                "regime": regime, "chg24h": chg24h
            })
            with open('shadow_range_filtered.json', 'w') as f:
                json.dump(log, f, indent=2)
        else:
            print("  -> No DIP/TOP signal.")
    else:
        print("  -> Not in range/chop. No action.")

if __name__ == "__main__":
    main()
