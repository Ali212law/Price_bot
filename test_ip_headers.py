import requests
import socket

NOBITEX_IP = "185.143.232.201"

print("=== TEST IP + HEADERS ===")

# ۱. IP خروجی GitHub Actions
try:
    r = requests.get("https://api.ipify.org", timeout=20)
    print(f"OUTBOUND IP: {r.text}")
except Exception as e:
    print(f"IP error: {e}")

# ۲. آپدیت hosts
with open("/etc/hosts", "a") as f:
    f.write(f"\n{NOBITEX_IP} api.nobitex.ir\n")

print(f"Hosts updated: {NOBITEX_IP}")

# ۳. تست نوبیتکس با ذخیره هدرها
try:
    r = requests.get(
        "https://api.nobitex.ir/v2/orderbook/BTCIRT",
        headers={"User-Agent": "TradingBot/1.0.0"},
        timeout=30
    )
    print(f"\n=== NOBITEX RESPONSE ===")
    print(f"Status: {r.status_code}")
    print(f"\n--- Response Headers ---")
    for k, v in r.headers.items():
        print(f"{k}: {v}")
    print(f"\n--- Body (first 500 chars) ---")
    print(r.text[:500])
except Exception as e:
    print(f"error: {type(e).__name__} - {e}")

# ۴. تست آبان‌تتر برای مقایسه
try:
    with open("/etc/hosts", "a") as f:
        f.write("\n185.143.234.130 api.abantether.com\n")
    
    r = requests.get(
        "https://api.abantether.com/api/v1/manager/otc/ticker",
        headers={"User-Agent": "TradingBot/1.0.0"},
        timeout=30
    )
    print(f"\n=== ABANTHER RESPONSE ===")
    print(f"Status: {r.status_code}")
    print(f"\n--- Response Headers ---")
    for k, v in r.headers.items():
        print(f"{k}: {v}")
except Exception as e:
    print(f"aban error: {type(e).__name__} - {e}")
