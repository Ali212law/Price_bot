import requests
import json
from datetime import datetime

BASE_URL = "https://api.wallex.ir"


def sep(title):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def try_endpoint(method, path, params=None):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, params=params, timeout=15)
        else:
            r = requests.post(url, json=params, timeout=15)
        
        status = r.status_code
        if status == 200:
            try:
                return True, status, r.json()
            except:
                return True, status, r.text[:500]
        else:
            return False, status, r.text[:300]
    except Exception as e:
        return False, "ERR", f"{type(e).__name__}: {e}"


# ═══════════════════════════════════════════
# ۱) لیست کامل نمادها و فیلتر BTC
# ═══════════════════════════════════════════

def list_all_symbols():
    sep("۱) LIST ALL SYMBOLS & FILTER BTC")
    
    success, status, data = try_endpoint("GET", "/v1/markets")
    if not success:
        print(f"❌ /v1/markets → {status}")
        print(data)
        return None
    
    result = data.get("result", {})
    symbols = result.get("symbols", {})
    
    print(f"✅ Total symbols: {len(symbols)}")
    print()
    
    # فیلتر BTC
    btc_symbols = [s for s in symbols.keys() if "BTC" in s.upper()]
    print(f"🎯 BTC-related symbols ({len(btc_symbols)}):")
    for s in sorted(btc_symbols):
        info = symbols[s]
        stats = info.get("stats", {})
        print(f"   {s}: lastPrice={stats.get('lastPrice', 'N/A')} | "
              f"bid={stats.get('bidPrice', 'N/A')} | "
              f"ask={stats.get('askPrice', 'N/A')}")
    
    # فیلتر TMN (تومان)
    tmn_symbols = [s for s in symbols.keys() if "TMN" in s.upper()]
    print(f"\n🎯 TMN (تومان) symbols ({len(tmn_symbols)}):")
    for s in sorted(tmn_symbols)[:30]:
        print(f"   {s}")
    if len(tmn_symbols) > 30:
        print(f"   ... و {len(tmn_symbols) - 30} تای دیگه")
    
    # فیلتر IRT
    irt_symbols = [s for s in symbols.keys() if "IRT" in s.upper()]
    print(f"\n🎯 IRT symbols ({len(irt_symbols)}):")
    for s in sorted(irt_symbols)[:20]:
        print(f"   {s}")
    
    return symbols


# ═══════════════════════════════════════════
# ۲) تست دقیق depth با نمادهای واقعی
# ═══════════════════════════════════════════

def test_depth_real_symbols(symbols):
    sep("۲) TESTING DEPTH WITH REAL SYMBOLS")
    
    if not symbols:
        print("❌ No symbols to test")
        return
    
    # اولویت: BTC/TMN → BTC/USDT → بقیه BTC
    btc_tmn = [s for s in symbols.keys() if "BTC" in s.upper() and "TMN" in s.upper()]
    btc_usdt = [s for s in symbols.keys() if "BTC" in s.upper() and "USDT" in s.upper()]
    btc_any = [s for s in symbols.keys() if "BTC" in s.upper()]
    
    test_symbols = list(set(btc_tmn + btc_usdt + btc_any))[:10]
    
    print(f"Testing {len(test_symbols)} symbols:")
    for sym in test_symbols:
        success, status, data = try_endpoint("GET", "/v1/depth", params={"symbol": sym})
        if success and isinstance(data, dict):
            result = data.get("result", {})
            bids = result.get("bids", []) if isinstance(result, dict) else []
            asks = result.get("asks", []) if isinstance(result, dict) else []
            print(f"✅ {sym} → {status} | bids={len(bids)} asks={len(asks)}")
            if bids:
                print(f"   Best bid: {bids[-1]}")
            if asks:
                print(f"   Best ask: {asks[-1]}")
        else:
            print(f"❌ {sym} → {status}")


# ═══════════════════════════════════════════
# ۳) تست مسیرهای مختلف orderbook
# ═══════════════════════════════════════════

def test_orderbook_paths():
    sep("۳) TESTING ORDERBOOK PATHS")
    
    paths = [
        "/v1/depth",
        "/v1/orderbook",
        "/v2/depth",
        "/v2/orderbook",
    ]
    
    symbols_to_try = ["BTCUSDT", "BTCTMN", "BTCUSDT"]
    
    for path in paths:
        for sym in symbols_to_try:
            success, status, data = try_endpoint("GET", path, params={"symbol": sym})
            if success and isinstance(data, dict):
                result = data.get("result", {})
                if isinstance(result, dict):
                    bids = result.get("bids", [])
                    asks = result.get("asks", [])
                    if bids or asks:
                        print(f"✅ {path}?symbol={sym} → {status} | bids={len(bids)} asks={len(asks)}")
                        if bids:
                            print(f"   Best bid: {bids[-1]}")
                        if asks:
                            print(f"   Best ask: {asks[-1]}")
                    else:
                        print(f"⚠️  {path}?symbol={sym} → {status} (empty)")
                else:
                    print(f"⚠️  {path}?symbol={sym} → {status} (not dict)")
            else:
                print(f"❌ {path}?symbol={sym} → {status}")


# ═══════════════════════════════════════════
# ۴) تست params مختلف برای trades
# ═══════════════════════════════════════════

def test_trades_params():
    sep("۴) TESTING TRADES PARAMS")
    
    # از نمادهایی که وجود دارن
    params_list = [
        {"symbol": "BTCUSDT"},
        {"symbol": "BTCUSDT", "limit": 10},
        {"symbol": "BTCUSDT", "count": 10},
    ]
    
    for params in params_list:
        success, status, data = try_endpoint("GET", "/v1/trades", params=params)
        if success and isinstance(data, dict):
            result = data.get("result", {})
            trades = result.get("trades", []) if isinstance(result, dict) else []
            print(f"✅ params={params} → {status} | trades={len(trades)}")
            if trades:
                print(f"   Latest: {trades[0]}")
        else:
            print(f"❌ params={params} → {status}")


# ═══════════════════════════════════════════
# ۵) نمایش نمونه از یه نماد کامل
# ═══════════════════════════════════════════

def show_sample_symbol(symbols):
    sep("۵) SAMPLE SYMBOL DETAIL")
    
    if not symbols:
        return
    
    # اولین نماد TMN
    for s, info in symbols.items():
        if "TMN" in s.upper() and "BTC" in s.upper():
            print(f"🎯 BTC/TMN Symbol: {s}")
            print(json.dumps(info, indent=2, ensure_ascii=False)[:2000])
            break
    else:
        # اگه BTC/TMN نبود، اولین TMN
        for s, info in symbols.items():
            if "TMN" in s.upper():
                print(f"🎯 Sample TMN Symbol: {s}")
                print(json.dumps(info, indent=2, ensure_ascii=False)[:2000])
                break
        else:
            # اولین USDT
            for s, info in symbols.items():
                if "USDT" in s.upper():
                    print(f"🎯 Sample USDT Symbol: {s}")
                    print(json.dumps(info, indent=2, ensure_ascii=False)[:2000])
                    break


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    print("\n" + "=" * 50)
    print("  WALLEX API TEST #3")
    print("=" * 50)
    print(f"Time: {datetime.now().isoformat()}")
    
    symbols = list_all_symbols()
    test_depth_real_symbols(symbols)
    test_orderbook_paths()
    test_trades_params()
    show_sample_symbol(symbols)
    
    print("\n" + "=" * 50)
    print("  DONE")
    print("=" * 50)


if __name__ == "__main__":
    main()
