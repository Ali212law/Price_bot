import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from decimal import Decimal

from config import (
    DRY_RUN, PAIR, MAX_TRADE_SIZE_USD, DEFAULT_SL_PCT, DEFAULT_TP_PCT,
    MAX_POSITIONS, STATE_FILE, LOG_FILE
)
from notifier import (
    notify_trade_opened, notify_trade_closed, notify, notify_halt
)
from safety_breaker import (
    is_halted, check_all_safety, record_trade,
    record_closed_position, load_state, save_state, trigger_halt
)

# ─── Binance API (برای دریافت کندل) ───
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

def fetch_klines(symbol="BNBUSDT", interval="4h", limit=100):
    """دریافت کندل‌های OHLCV از بایننس"""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'trades', 'taker_base', 'taker_quote', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        else:
            print(f"[BINANCE] HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"[BINANCE] Error: {e}")
        return None

def calculate_indicators(df):
    """محاسبه اندیکاتورهای M9: بولینگر، RSI، ATR"""
    df = df.copy()
    # Bollinger Bands (20, 2)
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['lower_bb'] = df['sma20'] - 2 * df['std20']
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR (14) برای حد ضرر/سود
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    
    return df.dropna().reset_index(drop=True)

def check_exit_conditions(position, current_price):
    """بررسی شرایط خروج از پوزیشن"""
    entry_price = Decimal(str(position['entry_price']))
    current_price = Decimal(str(current_price))
    
    pnl_pct = float((current_price - entry_price) / entry_price * 100)
    
    if pnl_pct >= DEFAULT_TP_PCT:
        return True, "TAKE_PROFIT", pnl_pct
    if pnl_pct <= -DEFAULT_SL_PCT:
        return True, "STOP_LOSS", pnl_pct
    
    return False, None, pnl_pct

def main():
    print(f"=== DEX Paper Trader (DRY_RUN={DRY_RUN}) ===")
    
    # ─── ۱. بررسی HALT ───
    if is_halted():
        print("🚨 HALT active - skipping all operations.")
        return
    
    # ─── ۲. دریافت داده ───
    print(f"Fetching {PAIR} klines from Binance...")
    df = fetch_klines(symbol="BNBUSDT", interval="4h", limit=100)
    if df is None or len(df) < 30:
        print("Insufficient data. Exiting.")
        return
    
    df = calculate_indicators(df)
    if len(df) < 2:
        print("Not enough data after indicators. Exiting.")
        return
    
    latest = df.iloc[-1]
    current_price = latest['close']
    lower_bb = latest['lower_bb']
    rsi = latest['rsi']
    atr = latest['atr']
    
    print(f"Current Price: {current_price:.2f} | Lower BB: {lower_bb:.2f} | RSI: {rsi:.2f}")
    
    # ─── ۳. بارگذاری وضعیت ───
    state = load_state()
    
    # ─── ۴. بررسی پوزیشن‌های باز ───
    for position in state['open_positions'][:]:
        should_exit, reason, pnl_pct = check_exit_conditions(position, current_price)
        
        if should_exit:
            entry = Decimal(str(position['entry_price']))
            current = Decimal(str(current_price))
            pnl_usd = float((current - entry) / entry * position['size_usd'])
            
            print(f"✅ Closing position {position['id']} | Reason: {reason} | PnL: {pnl_pct:.2f}% (${pnl_usd:.2f})")
            
            notify_trade_closed(position['symbol'], pnl_usd, pnl_pct, reason)
            record_closed_position(position['id'], pnl_usd)
            
            # ثبت در لاگ
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "CLOSE",
                "position_id": position['id'],
                "symbol": position['symbol'],
                "entry_price": position['entry_price'],
                "exit_price": current_price,
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd,
                "reason": reason
            }
            append_log(log_entry)
    
    # ─── ۵. بررسی سیگنال ورود جدید ───
    if len(state['open_positions']) < MAX_POSITIONS:
        # سیگنال M9: قیمت زیر باند پایین + RSI زیر 35
        if current_price <= lower_bb and rsi < 35:
            # بررسی مجوزهای ایمنی
            trade_size = float(MAX_TRADE_SIZE_USD)  # فعلاً همیشه ۱۰ دلار
            wallet_balance = 1000.0  # بالانس فرضی Paper
            
            allowed, reason = check_all_safety(trade_size, wallet_balance)
            
            if allowed:
                # محاسبه SL/TP بر اساس ATR (یا درصد ثابت)
                sl_price = current_price * (1 - DEFAULT_SL_PCT / 100)
                tp_price = current_price * (1 + DEFAULT_TP_PCT / 100)
                
                position = {
                    "id": f"pos_{int(time.time())}",
                    "symbol": PAIR,
                    "side": "LONG",
                    "entry_price": current_price,
                    "size_usd": trade_size,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "opened_at": datetime.now(timezone.utc).isoformat()
                }
                
                print(f"🟢 Opening LONG at {current_price:.2f} | Size: ${trade_size} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")
                
                notify_trade_opened(PAIR, "LONG", trade_size, current_price)
                record_trade(trade_size, position)
                
                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "OPEN",
                    "position_id": position['id'],
                    "symbol": PAIR,
                    "side": "LONG",
                    "entry_price": current_price,
                    "size_usd": trade_size,
                    "sl_price": sl_price,
                    "tp_price": tp_price
                }
                append_log(log_entry)
            else:
                print(f"⚠️ Signal blocked by safety: {reason}")
        else:
            print("No entry signal (price above lower BB or RSI >= 35).")
    else:
        print(f"Max positions reached ({len(state['open_positions'])}/{MAX_POSITIONS}).")
    
    print("=== Done ===")

def append_log(entry):
    """ثبت لاگ در فایل JSON"""
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append(entry)
    # نگه‌داری فقط ۵۰۰ لاگ آخر
    if len(logs) > 500:
        logs = logs[-500:]
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

if __name__ == "__main__":
    import os
    main()
