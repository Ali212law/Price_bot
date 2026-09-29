import requests
import socket

NOBITEX_IP = "185.143.232.201"

print("=== TEST NOBITEX (SERVER HEADERS) ===")

with open("/etc/hosts", "a") as f:
    f.write(f"\n{NOBITEX_IP} api.nobitex.ir\n")

print(f"Hosts updated: {NOBITEX_IP}")

# تست با هدر سروری (بدون Origin، بدون Sec-Fetch)
headers = {
    "User-Agent": "TradingBot/1.0.0",
    "Accept": "application/json"
}

try:
    r = requests.get("https://api.nobitex.ir/v2/orderbook/BTCIRT", headers=headers, timeout=30)
    print(f"\norderbook status: {r.status_code}")
    print(f"orderbook response: {r.text[:300]}")
except Exception as e:
    print(f"orderbook error: {type(e).__name__} - {e}")

# تست market stats
try:
    r = requests.get("https://api.nobitex.ir/market/stats?srcCurrency=btc&dstCurrency=rls", headers=headers, timeout=30)
    print(f"\nmarket stats status: {r.status_code}")
    print(f"market stats response: {r.text[:300]}")
except Exception as e:
    print(f"market stats error: {type(e).__name__} - {e}")

# تست با هدر کامل مرورگر برای مقایسه
headers_browser = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Origin": "https://nobitex.ir",
    "Accept": "application/json"
}

try:
    r = requests.get("https://api.nobitex.ir/v2/orderbook/BTCIRT", headers=headers_browser, timeout=30)
    print(f"\nbrowser headers status: {r.status_code}")
    print(f"browser headers response: {r.text[:200]}")
except Exception as e:
    print(f"browser headers error: {type(e).__name__} - {e}")
