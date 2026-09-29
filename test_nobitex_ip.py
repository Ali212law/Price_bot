import requests
import socket

NOBITEX_IP = "185.143.232.201"

print("=== TEST NOBITEX IP ===")

# آپدیت hosts
with open("/etc/hosts", "a") as f:
    f.write(f"\n{NOBITEX_IP} api.nobitex.ir\n")

print(f"Hosts updated: {NOBITEX_IP} api.nobitex.ir")

# تست resolve
try:
    ip = socket.gethostbyname("api.nobitex.ir")
    print(f"socket nobitex: {ip}")
except Exception as e:
    print(f"socket error: {e}")

# تست ۱: orderbook
try:
    r = requests.get("https://api.nobitex.ir/v2/orderbook/BTCIRT", timeout=30)
    print(f"\norderbook status: {r.status_code}")
    print(f"orderbook response: {r.text[:300]}")
except Exception as e:
    print(f"orderbook error: {type(e).__name__} - {e}")

# تست ۲: market stats
try:
    r = requests.get("https://api.nobitex.ir/market/stats?srcCurrency=btc&dstCurrency=rls", timeout=30)
    print(f"\nmarket stats status: {r.status_code}")
    print(f"market stats response: {r.text[:300]}")
except Exception as e:
    print(f"market stats error: {type(e).__name__} - {e}")
