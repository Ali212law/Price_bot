import requests
import os
import json
from datetime import datetime

WALLEX_API_KEY = os.environ.get("WALLEX_API_KEY", "")

BASE_URL = "https://api.wallex.ir"


def print_separator(title):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def test_market_stats():
    """تست API عمومی - آمار بازار"""
    print_separator("۱) TEST PUBLIC API - Market Stats")
    try:
        url = f"{BASE_URL}/v1/market/stats"
        print(f"URL: {url}")
        r = requests.get(url, timeout=15)
        print(f"Status Code: {r.status_code}")
        print(f"Headers:")
        print(f"  X-Request-ID: {r.headers.get('X-Request-ID', 'N/A')}")
        print(f"  Server: {r.headers.get('Server', 'N/A')}")
        print(f"  Content-Type: {r.headers.get('Content-Type', 'N/A')}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            print(f"   Success: {data.get('success', 'N/A')}")
            symbols = data.get("result", {}).get("symbols", {})
            print(f"   Symbols count: {len(symbols)}")
            if "BTCTMN" in symbols:
                btc = symbols["BTCTMN"]
                print(f"   BTCTMN stats:")
                print(f"     lastPrice: {btc.get('stats', {}).get('lastPrice', 'N/A')}")
                print(f"     bidPrice: {btc.get('stats', {}).get('bidPrice', 'N/A')}")
                print(f"     askPrice: {btc.get('stats', {}).get('askPrice', 'N/A')}")
            elif "BTCUSDT" in symbols:
                btc = symbols["BTCUSDT"]
                print(f"   BTCUSDT stats:")
                print(f"     lastPrice: {btc.get('stats', {}).get('lastPrice', 'N/A')}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_orderbook():
    """تست API عمومی - Order Book"""
    print_separator("۲) TEST PUBLIC API - Order Book")
    try:
        url = f"{BASE_URL}/v1/depth"
        params = {"symbol": "BTCTMN"}
        print(f"URL: {url}")
        print(f"Params: {params}")
        r = requests.get(url, params=params, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            print(f"   Success: {data.get('success', 'N/A')}")
            result = data.get("result", {})
            print(f"   Symbol: {result.get('symbol', 'N/A')}")
            bids = result.get("bids", [])
            asks = result.get("asks", [])
            print(f"   Bids count: {len(bids)}")
            print(f"   Asks count: {len(asks)}")
            if bids:
                print(f"   Best Bid: {bids[-1] if bids else 'N/A'}")
            if asks:
                print(f"   Best Ask: {asks[-1] if asks else 'N/A'}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_trades():
    """تست API عمومی - معاملات اخیر"""
    print_separator("۳) TEST PUBLIC API - Trades")
    try:
        url = f"{BASE_URL}/v1/trades"
        params = {"symbol": "BTCTMN"}
        r = requests.get(url, params=params, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            result = data.get("result", {})
            trades = result.get("trades", [])
            print(f"   Trades count: {len(trades)}")
            if trades:
                print(f"   Latest trade: {trades[0]}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_private_profile():
    """تست API خصوصی - Profile"""
    print_separator("۴) TEST PRIVATE API - Profile")
    if not WALLEX_API_KEY:
        print("⚠️  WALLEX_API_KEY تنظیم نشده - SKIP")
        print("   برای تست، API Key رو در Secrets اضافه کن")
        return None
    
    try:
        url = f"{BASE_URL}/v1/account/profile"
        headers = {"x-api-key": WALLEX_API_KEY}
        r = requests.get(url, headers=headers, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS - API Key کار می‌کنه!")
            print(f"   Response: {json.dumps(data, ensure_ascii=False)[:300]}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_markets():
    """تست API عمومی - Markets List"""
    print_separator("۵) TEST PUBLIC API - Markets")
    try:
        url = f"{BASE_URL}/v1/market/stats"
        r = requests.get(url, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            symbols = data.get("result", {}).get("symbols", {})
            print(f"\n✅ SUCCESS!")
            print(f"   Total symbols: {len(symbols)}")
            
            # پیدا کردن symbolهای مرتبط با BTC
            btc_symbols = [s for s in symbols.keys() if "BTC" in s]
            print(f"   BTC symbols: {btc_symbols[:10]}")
            
            # لیست همه‌ی symbolها
            print(f"   All symbols: {list(symbols.keys())[:20]}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def main():
    print("\n" + "=" * 50)
    print("  WALLEX API TEST")
    print("=" * 50)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"API Key: {'SET' if WALLEX_API_KEY else 'NOT SET'}")
    
    results = {}
    results["market_stats"] = test_market_stats()
    results["orderbook"] = test_orderbook()
    results["trades"] = test_trades()
    results["private_profile"] = test_private_profile()
    results["markets_list"] = test_markets()
    
    print_separator("SUMMARY")
    for name, result in results.items():
        if result is True:
            print(f"✅ {name}: SUCCESS")
        elif result is False:
            print(f"❌ {name}: FAILED")
        else:
            print(f"⚠️  {name}: SKIPPED")
    
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
