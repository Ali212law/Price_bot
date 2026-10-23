import requests
import json

def test_arzplus():
    # 1. Test public endpoint (markets)
    print("Testing Arzplus public API...")
    try:
        r = requests.get("https://api.arzplus.net/api/v1/market/symbols/", timeout=15)
        print(f"Symbols endpoint status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Received {len(data)} markets.")
            # Look for BTCIRT
            btc = next((m for m in data if m.get("name") == "BTCIRT"), None)
            if btc:
                print(f"BTCIRT found: maker_fee={btc.get('maker_fee')}, taker_fee={btc.get('taker_fee')}")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Test kline endpoint (guessing common patterns)
    print("\nTesting kline endpoint...")
    for endpoint in ["/market/kline", "/market/klines", "/market/candles"]:
        url = f"https://api.arzplus.net/api/v1{endpoint}?symbol=BTCIRT&interval=4h&limit=10"
        try:
            r = requests.get(url, timeout=10)
            print(f"  {endpoint} -> {r.status_code}")
            if r.status_code == 200:
                print(f"    ✅ Works! Response: {r.text[:200]}")
                break
        except:
            pass

if __name__ == "__main__":
    test_arzplus()
