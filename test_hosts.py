import subprocess
import requests
import socket

print("=== TEST HOSTS ===")

# اضافه کردن IP آبان‌تتر به hosts
with open("/etc/hosts", "a") as f:
    f.write("\n185.143.234.130 api.abantether.com\n")
    f.write("185.143.233.130 api.abantether.com\n")

print("Hosts updated")

# تست resolve
try:
    ip = socket.gethostbyname("api.abantether.com")
    print(f"socket aban: {ip}")
except Exception as e:
    print(f"socket aban error: {e}")

# تست اتصال
try:
    r = requests.get("https://api.abantether.com/api/v1/manager/otc/ticker", timeout=30)
    print(f"aban status: {r.status_code}")
    print(f"aban response: {r.text[:300]}")
except Exception as e:
    print(f"aban error: {type(e).__name__} - {e}")
