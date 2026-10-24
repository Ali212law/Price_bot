import requests
import json

def test_exchange(name, base_url, endpoints):
    print(f"\n{'='*50}")
    print(f"  TESTING: {name}")
    print(f"{'='*50}")
    
    for ep_name, url in endpoints.items():
        print(f"  Testing {ep_name}...")
        try:
            r = requests.get(url, timeout=10)
            print(f"    Status: {r.status_code}")
            if r.status_code == 200:
                print(f"    ✅ WORKS! Preview: {r.text[:100]}")
        except Exception as e:
            print(f"    ❌ Connection Error: {e}")

def main():
    # ۱. اوام‌پی‌فینکس (Ompfinex)
    test_exchange("Ompfinex", "", {
        "Markets": "https://api.ompfinex.com/v1/market/list",
        "OrderBook": "https://api.ompfinex.com/v1/market/orderbook?symbol=BTCIRT",
        "Candles (OHLCV)": "https://api.ompfinex.com/v1/market/ohlc?symbol=BTCIRT&resolution=240"
    })

    # ۲. تبدیل (Tabdeal)
    test_exchange("Tabdeal", "", {
        "Markets": "https://api.tabdeal.org/api/v1/market",
        "OrderBook": "https://api.tabdeal.org/api/v1/market/orderbook/BTCIRT",
        "Candles (OHLCV)": "https://api.tabdeal.org/api/v1/market/ohlc/BTCIRT"
    })

    # ۳. اکسیر (Exir)
    test_exchange("Exir", "", {
        "Markets": "https://api.exir.io/v2/markets",
        "OrderBook": "https://api.exir.io/v2/orderbooks?symbol=btc-irt",
        "Candles (OHLCV)": "https://api.exir.io/v2/chart?symbol=btc-irt&resolution=240"
    })

    # ۴. تگ‌پی (Tagpay)
    test_exchange("Tagpay", "", {
        "Markets": "https://api.tagpay.ir/v1/markets",
        "OrderBook": "https://api.tagpay.ir/v1/orderbook/BTCIRT",
        "Candles (OHLCV)": "https://api.tagpay.ir/v1/ohlc/BTCIRT"
    })

if __name__ == "__main__":
    main()
