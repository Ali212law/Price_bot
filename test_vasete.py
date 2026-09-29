import requests

urls = {
    "Navasan": "https://www.navasan.net/",
    "Alanchand": "https://alanchand.com/",
    "MajidAPI-Nobitex": "https://api.majidapi.ir/price/nobitex?currency=btc",
}

for name, url in urls.items():
    try:
        print(f"\n=== {name} ===")
        r = requests.get(url, timeout=20)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
