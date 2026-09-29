import requests
from bs4 import BeautifulSoup
import re

def test_navasan_btc():
    urls = [
        "https://www.navasan.net/price/btc",
        "https://www.navasan.net/",
    ]
    for url in urls:
        try:
            print(f"\n=== {url} ===")
            r = requests.get(url, timeout=20)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text()
                matches = re.findall(r'بیت[\s]*کوین[\s\S]{0,300}?([\d,]{8,})', text)
                print(f"BTC Matches: {matches[:5]}")
                big_numbers = re.findall(r'[\d,]{10,}', text)
                print(f"Big Numbers: {big_numbers[:10]}")
        except Exception as e:
            print(f"Error: {e}")

test_navasan_btc()
