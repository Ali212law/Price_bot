import requests
import json

def check_orderbook():
    base_url = "https://publicapi.ramzinex.com/exchange/api/v1.0"
    
    # جفت‌ارزهای هدف (بر اساس pair_id در رمزینکس)
    # برای مثال pair_id=11 معمولاً BTCIRT است
    pairs = {
        "BTCIRT (11)": 11,
        "ETHIRT (20)": 20, # حدسی، باید بررسی شود
        "XRPIRT (50)": 50,
    }

    print("Testing Ramzinex Order Book Depth...\n")
    
    for name, pair_id in pairs.items():
        url = f"{base_url}/exchange/orderbooks/{pair_id}/buys_sells"
        try:
            r = requests.get(url, timeout=15)
            print(f"--- {name} ---")
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if "data" in data and "buys" in data["data"] and "sells" in data["data"]:
                    buys = data["data"]["buys"]
                    sells = data["data"]["sells"]
                    
                    best_bid = buys[0][0] if buys else 0
                    best_ask = sells[0][0] if sells else 0
                    
                    # محاسبه عمق در ۱٪ اول بازار
                    bid_volume_1pct = sum([b[1] for b in buys if b[0] >= best_bid * 0.99])
                    ask_volume_1pct = sum([s[1] for s in sells if s[0] <= best_ask * 1.01])
                    
                    print(f"  Best Bid: {best_bid:,.0f} | Best Ask: {best_ask:,.0f}")
                    print(f"  Spread: {((best_ask - best_bid) / best_bid) * 100:.2f}%")
                    print(f"  Depth within 1% (Bids): {bid_volume_1pct:,.2f}")
                    print(f"  Depth within 1% (Asks): {ask_volume_1pct:,.2f}")
                else:
                    print("  Unexpected data format.")
            else:
                print(f"  Error: {r.text[:100]}")
        except Exception as e:
            print(f"  Connection Error: {e}")
        print()

if __name__ == "__main__":
    check_orderbook()
