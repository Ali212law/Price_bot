import requests
import time

def test_exir():
    base_url = "https://api.exir.io/v2"
    now = int(time.time())
    month_ago = now - (30 * 24 * 3600)
    
    print("Testing Exir OHLCV with different parameters...\n")

    # تست با فرمت‌های مختلف نماد، resolution و اضافه کردن زمان
    symbols = ["btc-irt", "btc-usdt"]
    resolutions = ["240", "4h", "4H"]
    
    for sym in symbols:
        for res in resolutions:
            print(f"--- Testing Symbol: {sym} | Resolution: {res} ---")
            
            # مسیر ۱: با اضافه کردن from و to
            url1 = f"{base_url}/chart?symbol={sym}&resolution={res}&from={month_ago}&to={now}"
            try:
                r = requests.get(url1, timeout=10)
                print(f"  [/chart with timestamps] Status: {r.status_code}")
                if r.status_code == 200:
                    print(f"    ✅✅✅ SUCCESS! Preview: {r.text[:150]}")
                    return
                else:
                    print(f"    Response: {r.text[:100]}")
            except Exception as e:
                print(f"    Error: {e}")

            # مسیر ۲: مسیر استاندارد UDF (که در خیلی از صرافی‌ها استفاده می‌شود)
            url2 = f"{base_url}/udf/history?symbol={sym}&resolution={res}&from={month_ago}&to={now}"
            try:
                r2 = requests.get(url2, timeout=10)
                print(f"  [/udf/history with timestamps] Status: {r2.status_code}")
                if r2.status_code == 200:
                    print(f"    ✅✅✅ SUCCESS! Preview: {r2.text[:150]}")
                    return
                else:
                    print(f"    Response: {r2.text[:100]}")
            except Exception as e:
                print(f"    Error: {e}")

    print("\n❌ Could not find the correct OHLCV endpoint.")

if __name__ == "__main__":
    test_exir()
