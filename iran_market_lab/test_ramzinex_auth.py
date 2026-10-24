import requests
import os
import base64

def test_auth_methods():
    api_key = os.environ.get("RAMZINEX_API_KEY")
    secret = os.environ.get("RAMZINEX_SECRET")
    
    if not api_key or not secret:
        print("❌ خطا: متغیرهای محیطی تنظیم نشده‌اند.")
        return

    # آدرس صحیح بر اساس مستندات (با پیشوند api.)
    url = "https://api.ramzinex.com/exchange/api/v1.0/users/funds"
    print(f"در حال تست احراز هویت روی: {url}\n")

    # روش ۱: Bearer + API Key در هدر
    headers1 = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # روش ۲: Bearer + Secret در هدر
    headers2 = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json"
    }

    # روش ۳: Basic Auth (ترکیب Key و Secret با base64)
    auth_str = f"{api_key}:{secret}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    headers3 = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json"
    }

    # روش ۴: هدرهای اختصاصی (x-api-key و x-api-secret)
    headers4 = {
        "x-api-key": api_key,
        "x-api-secret": secret,
        "Content-Type": "application/json"
    }

    # روش ۵: ارسال در Query Params
    params5 = {
        "api_key": api_key,
        "secret": secret
    }

    methods = [
        ("Bearer API Key", headers1, None),
        ("Bearer Secret", headers2, None),
        ("Basic Auth", headers3, None),
        ("x-api-key headers", headers4, None),
        ("Query Params", {}, params5)
    ]

    for name, headers, params in methods:
        print(f"--- تست {name} ---")
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            print(f"وضعیت: {r.status_code}")
            if r.status_code == 200:
                print(f"✅✅✅ موفقیت! روش درست پیدا شد: {name}")
                print(f"پاسخ: {r.text[:200]}")
                return
            elif r.status_code == 401 or r.status_code == 403:
                print(f"  (خطای احراز هویت: {r.status_code})")
            else:
                print(f"  پاسخ: {r.text[:100]}")
        except Exception as e:
            print(f"  خطای اتصال: {e}")
        print()

if __name__ == "__main__":
    test_auth_methods()
