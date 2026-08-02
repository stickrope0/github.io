import requests
from bs4 import BeautifulSoup
import re

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ja"}

theater_urls = {
    "3022": ("teatoru_shinjuku",   "https://eiga.com/theater/13/130201/3022/"),
    "3020": ("cinemart_shinjuku",  "https://eiga.com/theater/13/130201/3020/"),
    "3322": ("kino_shinjuku",      "https://eiga.com/theater/13/130201/3322/"),
    "3026": ("musashino",          "https://eiga.com/theater/13/130201/3026/"),
    "3018": ("ks_cinema",          "https://eiga.com/theater/13/130201/3018/"),
}

import time
for tid, (name, url) in theater_urls.items():
    print("\n" + "="*50)
    print(name, url)
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    
    secs = soup.select("section[id]")
    print(f"  section[id] count: {len(secs)}")
    
    # td[data-date] 内のボタン要素のクラスを確認
    tds = soup.select("td[data-date]")
    print(f"  td[data-date] count: {len(tds)}")
    if tds:
        td = tds[0]
        print("  最初のtd内の要素:")
        for child in td.children:
            if hasattr(child, "name") and child.name:
                print(f"    <{child.name} class={child.get('class')}> text={repr(child.get_text(strip=True)[:20])}")
    time.sleep(2)
