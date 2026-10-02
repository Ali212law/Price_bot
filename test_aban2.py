import socket
import requests
import json
import os

ABAN_API_KEY = os.environ.get("ABAN_API_KEY", "")
ABAN_IP = "185.143.234.130"
ABAN_HOST = "api.abantether.com"

# ═══════════════════════════════════════════
# FIX: Override DNS (بدون sudo / بدون /etc/hosts)
# ═══════════════════════════════════════════
_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, *args, **kwargs):
    if host == ABAN_HOST:
        return _original_getaddrinfo(ABAN_IP, *args, **kwargs)
    return _original_getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo


def test_aban_ticker():
    print("=" * 50)
    print("TEST ABAN TETHER TICKER")
    print("=" * 50)

    print(f"ABAN_API_KEY: {'SET' if ABAN_API_KEY else 'NOT SET'}")
    print(f"ABAN_IP: {ABAN_IP}")
    print(f"ABAN_HOST: {ABAN_HOST}")

    # تست resolve
    try:
        resolved = socket.gethostbyname(ABAN_HOST)
        print(f"Resolved: {resolved}")
    except Exception as e:
        print(f"Resolve Error: {e}")
        return

    # تست API
    url = f"https://{ABAN_HOST}/api/v1/manager/otc/ticker"
    headers = {
        "Authorization": ABAN_API_KEY,
        "Content-Type": "application/json",
    }

    print(f"\nURL: {url}")

    try:
        r = requests.get(url, headers=headers, timeout=30)
        print(f"Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS")
            print(f"Response (first 500 chars):")
            print(json.dumps(data, ensure_ascii=False)[:500])

            # استخراج BTC
            try:
                btc_data = data["data"]["markets"]["BTCIRT"]
                buy = float(btc_data["buy_price"])
                sell = float(btc_data["sell_price"])
                mid = (buy + sell) / 2
                spread_pct = ((sell - buy) / buy * 100) if buy else 0

                print(f"\n📊 BTC/IRT (AbanTether):")
                print(f"  Buy (خرید از کاربر): {buy:,.0f}")
                print(f"  Sell (فروش به کاربر): {sell:,.0f}")
                print(f"  Mid: {mid:,.0f}")
                print(f"  Spread: {spread_pct:.4f}%")
            except KeyError as e:
                print(f"\n⚠️ KeyError: {e}")
                print(f"Available keys: {list(data.get('data', {}).get('markets', {}).keys())[:10]}")
        else:
            print(f"\n❌ FAILED")
            print(f"Response: {r.text[:500]}")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")


def test_aban_balance():
    print("\n" + "=" * 50)
    print("TEST ABAN TETHER BALANCE")
    print("=" * 50)

    url = f"https://{ABAN_HOST}/accounting/balances"
    headers = {
        "Authorization": ABAN_API_KEY,
        "Content-Type": "application/json",
    }

    print(f"URL: {url}")

    try:
        r = requests.get(url, headers=headers, timeout=30)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"\n✅ SUCCESS")
            print(f"Response: {json.dumps(data, ensure_ascii=False)[:500]}")
        else:
            print(f"❌ FAILED: {r.text[:300]}")
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")


def main():
    test_aban_ticker()
    test_aban_balance()


if __name__ == "__main__":
    main()
