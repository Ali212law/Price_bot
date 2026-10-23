import requests
import time
import json
from datetime import datetime, timezone

def test_arzplus_ohlcv():
    symbol = "BTCIRT"
    resolution = "240"  # استاندارد TradingView برای 4 ساعت
    
    # محاسبه بازه زمانی ۲ سال پیش تا الان (به ثانیه)
    now = int(time.time())
    two_years_ago = now - (2 * 365 * 24 * 3600)
    
    print(f"Requesting {symbol} from {two_years_ago} to {now} with resolution={resolution}")
    
    url = "https://api.arzplus.net/api/v1/market/tradingview/ohlcv"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": two_years_ago,
        "to": now
    }
    
    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"✅ SUCCESS! Received {len(data)} candles.")
                
                # نمایش ۳ کندل اول
                for i in range(min(3, len(data))):
                    candle = data[i]
                    dt = datetime.fromtimestamp(candle['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                    print(f"  Candle {i+1}: Time={dt}, Close={candle['close']}, Volume={candle['volume']}")
                
                # بررسی فاصله زمانی (باید ۴ ساعت باشد)
                if len(data) > 1:
                    diff_ms = data[1]['time'] - data[0]['time']
                    diff_hours = diff_ms / (1000 * 3600)
                    print(f"Time difference between candles: {diff_hours} hours")
                    
                # ذخیره در فایل
                with open("data/BTCIRT_test_4h.json", "w") as f:
                    json.dump(data, f, indent=2)
                print("Saved to data/BTCIRT_test_4h.json")
            else:
                print("❌ Data is empty or not a list.")
                print(r.text[:200])
        else:
            print(f"❌ Error Response: {r.text[:200]}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_arzplus_ohlcv()
