import requests

urls = {
    "Nobitex-Orderbook": "https://api.nobitex.ir/v2/orderbook/BTCIRT",
    "Nobitex-Stats": "https://api.nobitex.ir/v2/stats",
    "Nobitex-Market": "https://api.nobitex.ir/market/stats?srcCurrency=btc&dstCurrency=rls",
}

for name, url in urls.items():
    try:
        print(f"\n=== {name} ===")
        r = requests.get(url, timeout=20)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")
