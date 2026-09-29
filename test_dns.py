import subprocess
import socket

print("=== TEST DNS ===")

# تست ۱: getent hosts nobitex
try:
    result = subprocess.run(["getent", "hosts", "api.nobitex.ir"], capture_output=True, text=True, timeout=10)
    print(f"getent nobitex stdout: {result.stdout.strip()}")
    print(f"getent nobitex stderr: {result.stderr.strip()}")
except Exception as e:
    print(f"getent nobitex error: {e}")

# تست ۲: getent hosts abantether
try:
    result = subprocess.run(["getent", "hosts", "api.abantether.com"], capture_output=True, text=True, timeout=10)
    print(f"getent aban stdout: {result.stdout.strip()}")
    print(f"getent aban stderr: {result.stderr.strip()}")
except Exception as e:
    print(f"getent aban error: {e}")

# تست ۳: socket resolve nobitex
try:
    ip = socket.gethostbyname("api.nobitex.ir")
    print(f"socket nobitex: {ip}")
except Exception as e:
    print(f"socket nobitex error: {type(e).__name__} - {e}")

# تست ۴: socket resolve abantether
try:
    ip = socket.gethostbyname("api.abantether.com")
    print(f"socket aban: {ip}")
except Exception as e:
    print(f"socket aban error: {type(e).__name__} - {e}")

# تست ۵: socket resolve google (کنترل)
try:
    ip = socket.gethostbyname("google.com")
    print(f"socket google: {ip}")
except Exception as e:
    print(f"socket google error: {type(e).__name__} - {e}")
