import requests

def test_exir():
    base_url = "https://api.exir.io/v2"
    symbol = "btc-usdt" # فرمت صحیح بر اساس خروجی اوردر بوک
    print(f"Testing Exir API with symbol: {symbol}\n")

    # ۱. تست لیست بازارها (Markets)
    print("1. Testing Markets:")
    for path in ["/markets", "/constants", "/market"]:
        try:
            r = requests.get(base_url + path, timeout=10)
            print(f"   [{r.status_code}] {path} -> {r.text[:80]}")
        except Exception as e:
            print(f"   [ERROR] {path} -> {e}")

    # ۲. تست دریافت داده تاریخی (OHLCV)
    print("\n2. Testing OHLCV (Historical Data):")
    paths = [
        f"/chart?symbol={symbol}&resolution=240",
        f"/udf/history?symbol={symbol}&resolution=240",
        f"/market/chart?symbol={symbol}&resolution=240",
        f"/ohlc?symbol={symbol}&resolution=240"
    ]
    for path in paths:
        try:
            r = requests.get(base_url + path, timeout=10)
            print(f"   [{r.status_code}] {path} -> {r.text[:80]}")
        except Exception as e:
            print(f"   [ERROR] {path} -> {e}")

if __name__ == "__main__":
    test_exir()
