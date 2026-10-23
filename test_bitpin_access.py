import requests
import sys

def test_bitpin():
    url = "https://api.bitpin.org/api/v1/mkt/markets/"
    print(f"Testing connection to: {url}")
    
    try:
        # Test with a 15-second timeout
        r = requests.get(url, timeout=15)
        
        print(f"HTTP Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"SUCCESS! Received {len(data)} markets.")
            print("Sample market:", data[0].get('title', 'Unknown') if isinstance(data, list) and len(data) > 0 else "N/A")
            print("\nCONCLUSION: Bitpin API is accessible from GitHub Actions (Foreign IP).")
        else:
            print(f"FAILED! Response: {r.text[:200]}")
            print("\nCONCLUSION: Bitpin API returned an error. Possible IP restriction.")
            
    except requests.exceptions.Timeout:
        print("FAILED! Connection timed out.")
        print("\nCONCLUSION: Bitpin API is NOT reachable (Timeout). Likely IP restricted.")
    except requests.exceptions.ConnectionError:
        print("FAILED! Connection error.")
        print("\nCONCLUSION: Cannot establish connection. DNS or Firewall block.")
    except Exception as e:
        print(f"FAILED! Unexpected error: {e}")

if __name__ == "__main__":
    test_bitpin()
