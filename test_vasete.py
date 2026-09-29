import requests

urls = {
    "Navasan-API": "https://api.navasan.tech/latest/?api_key=free",
    "Alanchand-API-v1": "https://api.alanchand.com/v1/price/btc",
    "Alanchand-API-v2": "https://api.alanchand.com/api/v1/currency/btc",
    "Alanchand-Price": "https://alanchand.com/price/btc",
}

for name, url in urls.items():
    try:
        print(f"\n=== {name} ===")
        r = requests.get(url, timeout=20)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")
