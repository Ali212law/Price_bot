import requests

def test_ohlcv_endpoints():
    print("Testing Ramzinex OHLCV endpoints...")
    base_url = "https://publicapi.ramzinex.com/exchange/api/v1.0"
    pair_id = 11 # BTCIRT
    
    # لیست مسیرهای احتمالی برای دریافت کندل در رمزینکس
    endpoints = [
        f"/exchange/chart/ohlc/{pair_id}?resolution=240",
        f"/exchange/chart/candles/{pair_id}?resolution=240",
        f"/exchange/chart/klines/{pair_id}?resolution=240",
        f"/exchange/pairs/{pair_id}/ohlc?resolution=240",
        f"/exchange/udf/history?symbol=BTCIRT&resolution=240",
        f"/exchange/chart/tradingview/ohlcv?symbol={pair_id}&resolution=240"
    ]
    
    for ep in endpoints:
        url = base_url + ep
        try:
            r = requests.get(url, timeout=15)
            print(f"[{r.status_code}] {ep}")
            if r.status_code == 200:
                print(f"    ✅ WORKS! Preview: {r.text[:150]}")
        except Exception as e:
            print(f"[ERROR] {ep} -> {e}")

if __name__ == "__main__":
    test_ohlcv_endpoints()
