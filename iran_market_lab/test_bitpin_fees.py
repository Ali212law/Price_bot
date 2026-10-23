import requests
import json

def test_fees():
    url = "https://api.bitpin.org/api/v1/mkt/commissions/"
    print(f"Fetching commissions from: {url}")
    
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                print(f"Received {len(data)} records.")
                for item in data:
                    if isinstance(item, dict) and item.get("symbol") == "BTC_IRT":
                        print("\n--- BTC_IRT Commissions ---")
                        print(json.dumps(item, indent=2, ensure_ascii=False))
                        break
            elif isinstance(data, dict):
                print("\n--- Response Dictionary ---")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print("Unexpected data format:", type(data))
        else:
            print(f"HTTP Error: {r.status_code}")
            print(r.text[:500])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fees()
