import requests
import json

def test_endpoint(name, url, description):
    print(f"  [{name}] {description}...")
    try:
        r = requests.get(url, timeout=15)
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            # نمایش بخشی از پاسخ برای بررسی صحت داده
            text = r.text[:150].replace('\n', ' ')
            print(f"    Preview: {text}...")
            return True
        else:
            print(f"    Error: {r.text[:100]}")
            return False
    except Exception as e:
        print(f"    Connection Error: {e}")
        return False

def test_rastin():
    print("\n" + "="*50)
    print("  TESTING RASTIN EXCHANGE")
    print("="*50)
    base_url = "https://api.rastin.exchange/api/v1"
    
    # 1. Test basic market info (IP check)
    test_endpoint("RASTIN", f"{base_url}/market/list", "Markets List (IP Check)")
    
    # 2. Test Order Book
    test_endpoint("RASTIN", f"{base_url}/market/depth/BTCIRT", "Order Book (BTCIRT)")
    
    # 3. Test OHLCV (Trying common endpoints)
    test_endpoint("RASTIN", f"{base_url}/market/ohlcv?symbol=BTCIRT&resolution=240&limit=10", "OHLCV (Pattern 1)")
    test_endpoint("RASTIN", f"{base_url}/market/candles/BTCIRT?interval=4h", "OHLCV (Pattern 2)")

def test_ramzinex():
    print("\n" + "="*50)
    print("  TESTING RAMZINEX EXCHANGE")
    print("="*50)
    base_url = "https://publicapi.ramzinex.com/exchange/api/v1.0"
    pair_id = 11 # Standard for BTCIRT in Ramzinex
    
    # 1. Test basic market info (IP check)
    test_endpoint("RAMZINEX", f"{base_url}/exchange/pairs", "Pairs List (IP Check)")
    
    # 2. Test Order Book
    test_endpoint("RAMZINEX", f"{base_url}/exchange/orderbooks/{pair_id}/buys_sells", "Order Book (BTCIRT)")
    
    # 3. Test OHLCV
    test_endpoint("RAMZINEX", f"{base_url}/exchange/chart/ohlc?pair_id={pair_id}&resolution=240", "OHLCV (4H)")

if __name__ == "__main__":
    print("Starting API Tests...")
    test_rastin()
    test_ramzinex()
    print("\nTests Completed.")
