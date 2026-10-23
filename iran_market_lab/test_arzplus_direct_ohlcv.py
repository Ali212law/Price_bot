import requests
import json

def test_arzplus():
    print("Fetching symbols from Arzplus...")
    r = requests.get("https://api.arzplus.net/api/v1/market/symbols/", timeout=15)
    if r.status_code == 200:
        data = r.json()
        print("Sample symbols (first 3):")
        for s in data[:3]:
            print(json.dumps(s, indent=2, ensure_ascii=False))
        
        # پیدا کردن نماد بیت‌کوین
        btc_symbol = None
        for s in data:
            # بررسی فیلدهای name یا id
            name = str(s.get("name", ""))
            sid = str(s.get("id", ""))
            if "BTC" in name or "BTC" in sid:
                btc_symbol = s
                break
        
        if btc_symbol:
            print("\nFound BTC symbol object:", json.dumps(btc_symbol, ensure_ascii=False))
            symbol_name = btc_symbol.get("name")
            symbol_id = btc_symbol.get("id")
            
            # تلاش با فیلد name
            print(f"\nTesting OHLCV with 'name' = {symbol_name}")
            url = f"https://api.arzplus.net/api/v1/market/tradingview/ohlcv?symbol={symbol_name}&resolution=4h&countBack=10"
            r2 = requests.get(url, timeout=15)
            print(f"Status: {r2.status_code}")
            print(f"Response: {r2.text[:200]}")
            
            # اگر با name کار نکرد، تلاش با فیلد id
            if r2.status_code != 200 and symbol_id != symbol_name:
                print(f"\nTesting OHLCV with 'id' = {symbol_id}")
                url2 = f"https://api.arzplus.net/api/v1/market/tradingview/ohlcv?symbol={symbol_id}&resolution=4h&countBack=10"
                r3 = requests.get(url2, timeout=15)
                print(f"Status: {r3.status_code}")
                print(f"Response: {r3.text[:200]}")

if __name__ == "__main__":
    test_arzplus()
