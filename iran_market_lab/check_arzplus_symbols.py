import requests

def check_symbols():
    print("Fetching all symbols from Arzplus...")
    try:
        r = requests.get("https://api.arzplus.net/api/v1/market/symbols/", timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"Total symbols: {len(data)}\n")
            
            print("--- Symbols ending with 'IRT' (Toman pairs) ---")
            irt_pairs = []
            for s in data:
                name = s.get("name", "")
                if "IRT" in name:
                    irt_pairs.append(name)
                    print(f"  {name} (ID: {s.get('id')})")
            
            if not irt_pairs:
                print("No IRT pairs found! (Maybe they use TMN or RLS?)")
                print("\n--- Sample of all symbols (first 20) ---")
                for s in data[:20]:
                    print(f"  {s.get('name')}")
                    
        else:
            print(f"HTTP Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_symbols()
