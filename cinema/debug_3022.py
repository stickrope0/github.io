import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ja"}
url = "https://eiga.com/theater/13/130201/3022/"
r = requests.get(url, headers=HEADERS, timeout=15)
r.encoding = r.apparent_encoding
soup = BeautifulSoup(r.text, "html.parser")

print("=== section[id] (最初5件) ===")
for s in soup.select("section[id]")[:5]:
    print("  id=" + str(s.get("id")) + " data-title=" + repr(s.get("data-title", "")[:30]))

print("\n=== h2 tags (最初5件) ===")
for h2 in soup.find_all("h2")[:5]:
    print("  class=" + str(h2.get("class")) + " text=" + repr(h2.get_text(strip=True)[:40]))

print("\n=== div.movie-schedule count:", len(soup.select("div.movie-schedule")))
print("=== table.weekly-schedule count:", len(soup.select("table.weekly-schedule")))

secs = soup.select("section[id]")
if secs:
    print("\n=== 最初のsection HTML (先頭800文字) ===")
    print(str(secs[0])[:800])
else:
    print("\nsection[id] が見つかりません")
    print("body直下タグ:")
    for c in soup.body.children:
        if hasattr(c, "name") and c.name:
            print("  " + c.name + " class=" + str(c.get("class")) + " id=" + str(c.get("id")))
