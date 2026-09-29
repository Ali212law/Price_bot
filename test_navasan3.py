import requests
from bs4 import BeautifulSoup
import re

url = "https://www.navasan.net/price/btc"
r = requests.get(url, timeout=20)
soup = BeautifulSoup(r.text, "html.parser")

print("=== جستجوی دقیق ===")

text = soup.get_text()
idx = text.find("بیت کوین")
if idx > 0:
    snippet = text[idx:idx+500]
    print(f"Snippet around 'بیت کوین':")
    print(snippet)

print("\n=== همه اعداد بزرگ با متن اطراف ===")
for match in re.finditer(r'[\d,]{10,}', text):
    start = max(0, match.start() - 50)
    end = min(len(text), match.end() + 50)
    print(f"...{text[start:end]}...")
    print("---")
