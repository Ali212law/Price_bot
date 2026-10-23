import requests

def check_symbols():
    print("Fetching all symbols from Arzplus...")
    try:
        r = requests.get("https://api.arzplus.net/api/v1/market/symbols/", timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"Total symbols: {len(data)}\n")
            
            print("--- All Available Symbols ---")
            for s in data:
                name = s.get("name", "")
                base = s.get("base_asset", {}).get("symbol", "")
                quote = s.get("asset", {}).get("symbol", "") # در ارزپلاس، asset نقش quote را دارد
                print(f"  {name} (Base: {base}, Quote: {quote})")
                    
        else:
            print(f"HTTP Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_symbols()
