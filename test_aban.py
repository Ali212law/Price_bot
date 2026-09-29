import requests
import os

ABAN_API_KEY = os.environ["ABAN_API_KEY"]
headers = {"Authorization": ABAN_API_KEY, "Content-Type": "application/json"}

urls = [
    "https://api.abantether.com",
    "https://api.abantether.com/api/v1/manager/otc/ticker",
    "https://abantether.com",
]

for url in urls:
    try:
        print(f"\n=== TEST: {url} ===")
        r = requests.get(url, headers=headers, timeout=20)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
