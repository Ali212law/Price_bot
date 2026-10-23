import requests

def test_klines():
    print("Testing Arzplus kline endpoints...")
    base_url = "https://api.arzplus.net"
    
    # لیست مسیرهای احتمالی برای دریافت کندل
    endpoints = [
        "/api/v1/udf/history?symbol=BTCIRT&resolution=240&from=1700000000&to=1700100000",
        "/api/v1/market/history?symbol=BTCIRT&resolution=240&from=1700000000&to=1700100000",
        "/api/v1/market/ohlcv?symbol=BTCIRT&interval=4h",
        "/api/v1/market/kline/BTCIRT?interval=4h",
        "/api/v1/market/klines/BTCIRT?interval=4h",
        "/api/v1/market/chart?symbol=BTCIRT&interval=4h",
        "/api/v1/market/trades?symbol=BTCIRT" # اگر کندل نبود، شاید معاملات خرد باشد
    ]
    
    for ep in endpoints:
        url = base_url + ep
        try:
            r = requests.get(url, timeout=10)
            print(f"[{r.status_code}] {ep}")
            if r.status_code == 200:
                print(f"    ✅ WORKS! Preview: {r.text[:150]}")
        except Exception as e:
            print(f"[ERROR] {ep} -> {e}")

if __name__ == "__main__":
    test_klines()
