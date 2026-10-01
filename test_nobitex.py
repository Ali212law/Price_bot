import requests
import os
import json
from datetime import datetime

# === API Key (اختیاری) ===
API_KEY = os.environ.get("NOBITEX_API_KEY", "")

BASE_URL = "https://api.nobitex.ir"
TESTNET_URL = "https://testnetapiv2.nobitex.ir"


def print_separator(title):
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50)


def test_public_market():
    """تست API عمومی - Market Stats"""
    print_separator("۱) TEST PUBLIC API - Market Stats")
    try:
        url = f"{BASE_URL}/v2/market/stats"
        print(f"URL: {url}")
        r = requests.get(url, timeout=15)
        print(f"Status Code: {r.status_code}")
        print(f"Headers:")
        print(f"  X-Request-ID: {r.headers.get('X-Request-ID', 'N/A')}")
        print(f"  Server: {r.headers.get('Server', 'N/A')}")
        print(f"  Content-Type: {r.headers.get('Content-Type', 'N/A')}")
        print(f"  Date: {r.headers.get('Date', 'N/A')}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            btc = data.get("btc-rls", {})
            if btc:
                print(f"   BTC/RLS - last: {btc.get('latest', 'N/A')}")
                print(f"   BTC/RLS - dayChange: {btc.get('dayChange', 'N/A')}%")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_public_orderbook():
    """تست API عمومی - Order Book"""
    print_separator("۲) TEST PUBLIC API - Order Book")
    try:
        url = f"{BASE_URL}/v2/orderbook/BTCIRT"
        print(f"URL: {url}")
        r = requests.get(url, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            print(f"   Last Update: {data.get('lastUpdate', 'N/A')}")
            print(f"   Last Trade Price: {data.get('lastTradePrice', 'N/A')}")
            print(f"   Status: {data.get('status', 'N/A')}")
            asks = data.get("asks", [])
            bids = data.get("bids", [])
            if asks:
                print(f"   Best Ask: {asks[0]}")
            if bids:
                print(f"   Best Bid: {bids[0]}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_public_udf_history():
    """تست API عمومی - UDF History"""
    print_separator("۳) TEST PUBLIC API - UDF History")
    try:
        url = f"{BASE_URL}/v2/udf/history"
        params = {
            "symbol": "BTCIRT",
            "resolution": "60",
            "from": int(datetime.now().timestamp()) - 86400,
            "to": int(datetime.now().timestamp()),
        }
        print(f"URL: {url}")
        print(f"Params: {params}")
        r = requests.get(url, params=params, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS!")
            print(f"   Status: {data.get('s', 'N/A')}")
            print(f"   Candles count: {len(data.get('c', []))}")
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
    if not API_KEY:
        print("⚠️  NOBITEX_API_KEY تنظیم نشده - SKIP")
        print("   برای تست، API Key رو در Secrets اضافه کن")
        return None
    
    try:
        url = f"{BASE_URL}/users/profile"
        headers = {"Authorization": f"Token {API_KEY}"}
        print(f"URL: {url}")
        r = requests.get(url, headers=headers, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS - API Key کار می‌کنه!")
            print(f"   Status: {data.get('status', 'N/A')}")
            user = data.get("profile", {})
            if user:
                print(f"   User ID: {user.get('id', 'N/A')}")
                print(f"   Email: {user.get('email', 'N/A')}")
                print(f"   Level: {user.get('level', 'N/A')}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def test_testnet():
    """تست Testnet"""
    print_separator("۵) TEST TESTNET API")
    try:
        url = f"{TESTNET_URL}/v2/market/stats"
        print(f"URL: {url}")
        r = requests.get(url, timeout=15)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS - Testnet کار می‌کنه!")
            btc = data.get("btc-rls", {})
            if btc:
                print(f"   BTC/RLS: {btc.get('latest', 'N/A')}")
            return True
        else:
            print(f"\n❌ FAILED - Status {r.status_code}")
            print(f"   Response: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False


def main():
    print("\n" + "=" * 50)
    print("  NOBITEX API TEST")
    print("=" * 50)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"API Key: {'SET' if API_KEY else 'NOT SET'}")
    
    results = {}
    results["market_stats"] = test_public_market()
    results["orderbook"] = test_public_orderbook()
    results["udf_history"] = test_public_udf_history()
    results["private_profile"] = test_private_profile()
    results["testnet"] = test_testnet()
    
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
