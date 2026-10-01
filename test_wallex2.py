import requests
import json
from datetime import datetime

BASE_URL = "https://api.wallex.ir"


def sep(title):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def try_endpoint(method, path, params=None, headers=None):
    """یه endpoint رو تست می‌کنه و نتیجه رو برمی‌گردونه"""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, params=params, headers=headers, timeout=15)
        else:
            r = requests.post(url, json=params, headers=headers, timeout=15)
        
        status = r.status_code
        if status == 200:
            data = r.json()
            return True, status, data
        else:
            return False, status, r.text[:300]
    except Exception as e:
        return False, "ERR", f"{type(e).__name__}: {e}"


# ═══════════════════════════════════════════
# ۱) تست مسیرهای مختلف Market
# ═══════════════════════════════════════════

def test_market_paths():
    sep("۱) TESTING MARKET PATHS")
    
    paths = [
        "/v1/market/stats",
        "/v1/markets",
        "/v1/symbols",
        "/v1/market",
        "/v2/market/stats",
        "/v2/markets",
        "/v1/exchangeInfo",
        "/v1/market/stats/BTCUSDT",
    ]
    
    for path in paths:
        success, status, data = try_endpoint("GET", path)
        if success:
            print(f"✅ {path} → {status}")
            if isinstance(data, dict):
                result = data.get("result", data)
                if isinstance(result, dict):
                    keys = list(result.keys())[:5]
                    print(f"   Keys: {keys}")
                    if "symbols" in result:
                        symbols = result["symbols"]
                        print(f"   Symbols count: {len(symbols)}")
                        # لیست ۱۰ نماد اول
                        print(f"   First 10: {list(symbols.keys())[:10]}")
                elif isinstance(result, list):
                    print(f"   List count: {len(result)}")
                    if result:
                        print(f"   First item: {result[0]}")
        else:
            print(f"❌ {path} → {status}")
            if isinstance(data, str):
                print(f"   {data[:150]}")


# ═══════════════════════════════════════════
# ۲) تست Depth با نمادهای مختلف
# ═══════════════════════════════════════════

def test_depth_symbols():
    sep("۲) TESTING DEPTH WITH DIFFERENT SYMBOLS")
    
    symbols = ["BTCTMN", "BTCUSDT", "BTCIRT", "BTC-IRT", "BTC_TMN", "BTC"]
    
    for sym in symbols:
        success, status, data = try_endpoint("GET", "/v1/depth", params={"symbol": sym})
        if success:
            result = data.get("result", {})
            bids = result.get("bids", [])
            asks = result.get("asks", [])
            symbol_returned = result.get("symbol", "N/A")
            print(f"✅ symbol={sym} → {status} | returned_symbol={symbol_returned} | bids={len(bids)} asks={len(asks)}")
            if bids:
                print(f"   Best bid: {bids[-1]}")
            if asks:
                print(f"   Best ask: {asks[-1]}")
        else:
            print(f"❌ symbol={sym} → {status}")


# ═══════════════════════════════════════════
# ۳) تست Trades
# ═══════════════════════════════════════════

def test_trades_symbols():
    sep("۳) TESTING TRADES WITH DIFFERENT SYMBOLS")
    
    symbols = ["BTCTMN", "BTCUSDT", "BTCIRT"]
    
    for sym in symbols:
        success, status, data = try_endpoint("GET", "/v1/trades", params={"symbol": sym})
        if success:
            result = data.get("result", {})
            trades = result.get("trades", [])
            print(f"✅ symbol={sym} → {status} | trades={len(trades)}")
            if trades:
                print(f"   Latest: {trades[0]}")
        else:
            print(f"❌ symbol={sym} → {status}")


# ═══════════════════════════════════════════
# ۴) جستجوی BTCTMN در همه‌ی مسیرها
# ═══════════════════════════════════════════

def find_btc_symbol():
    sep("۴) FINDING BTC SYMBOL IN WALLEX")
    
    # از depth با نمادهای متداول
    print("Testing common symbol variations:")
    
    variations = [
        "BTCUSDT", "BTCTMN", "BTCIRT", "BTCTRY",
        "BTC-USDT", "BTC-TMN", "BTC-IRT",
        "BTC_USDT", "BTC_TMN", "BTC_IRT",
    ]
    
    found = []
    for sym in variations:
        success, status, data = try_endpoint("GET", "/v1/depth", params={"symbol": sym})
        if success:
            result = data.get("result", {})
            bids = result.get("bids", [])
            asks = result.get("asks", [])
            symbol_returned = result.get("symbol", "N/A")
            if bids or asks:
                found.append(sym)
                print(f"✅ {sym} WORKS | returned={symbol_returned} | bids={len(bids)} asks={len(asks)}")
                if bids:
                    print(f"   Best bid: {bids[-1]}")
    
    if not found:
        print("❌ هیچ نمادی جواب نداد")
    else:
        print(f"\n🎯 Found working symbols: {found}")


# ═══════════════════════════════════════════
# ۵) تست مسیرهای دیگه
# ═══════════════════════════════════════════

def test_other_paths():
    sep("۵) TESTING OTHER PATHS")
    
    paths = [
        "/v1/account/profile",
        "/v1/account/balances",
        "/v1/account/orders",
        "/v2/account/profile",
        "/v1/orderbook",
    ]
    
    for path in paths:
        success, status, data = try_endpoint("GET", path)
        if success:
            print(f"✅ {path} → {status}")
            if isinstance(data, dict):
                print(f"   Keys: {list(data.keys())[:5]}")
        else:
            print(f"❌ {path} → {status}")


# ═══════════════════════════════════════════
# ۶) تست کدوم نماد در trades
# ═══════════════════════════════════════════

def test_trades_auto():
    sep("۶) TESTING TRADES AUTO-DISCOVERY")
    
    # ابتدا markets رو می‌گیریم
    success, status, data = try_endpoint("GET", "/v1/markets")
    if success:
        print(f"✅ /v1/markets works!")
        result = data.get("result", [])
        if isinstance(result, list):
            print(f"   Markets count: {len(result)}")
            for m in result[:5]:
                print(f"   {m}")
        elif isinstance(result, dict):
            print(f"   Keys: {list(result.keys())[:10]}")
    else:
        print(f"❌ /v1/markets → {status}")


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    print("\n" + "=" * 50)
    print("  WALLEX API TEST #2")
    print("=" * 50)
    print(f"Time: {datetime.now().isoformat()}")
    
    test_market_paths()
    test_depth_symbols()
    test_trades_symbols()
    find_btc_symbol()
    test_other_paths()
    test_trades_auto()
    
    print("\n" + "=" * 50)
    print("  DONE")
    print("=" * 50)


if __name__ == "__main__":
    main()
