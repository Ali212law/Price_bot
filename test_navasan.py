import requests

urls = {
    "Navasan-Fiat": "https://raw.githubusercontent.com/HosseinOdd/Navasan-API/main/data/fiat.json",
    "Navasan-Gold": "https://raw.githubusercontent.com/HosseinOdd/Navasan-API/main/data/gold.json",
    "Navasan-Crypto": "https://raw.githubusercontent.com/HosseinOdd/Navasan-API/main/data/crypto.json",
    "Navasan-All": "https://raw.githubusercontent.com/HosseinOdd/Navasan-API/main/data/latest.json",
}

for name, url in urls.items():
    try:
        print(f"\n=== {name} ===")
        r = requests.get(url, timeout=20)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Keys: {list(data.keys())[:20]}")
            print(f"Sample: {str(data)[:300]}")
        else:
            print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
