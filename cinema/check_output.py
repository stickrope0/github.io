import json
from collections import Counter

with open("out/schedule_latest.json", encoding="utf-8") as f:
    data = json.load(f)

by_theater = Counter(r["theater_name"] for r in data)
print("=== 劇場別取得件数 ===")
for name, cnt in sorted(by_theater.items(), key=lambda x: -x[1]):
    print(f"  {cnt:3d} 行  {name}")

print()
print("=== サンプルデータ（各劇場1件）===")
seen = set()
for r in data:
    tn = r["theater_name"]
    if tn not in seen:
        seen.add(tn)
        print(f"  [{tn}]")
        print(f"    タイトル: {r['title']}")
        print(f"    公開日: {r['release_date']}  上映時間: {r['duration']}  レーティング: {r['rating']}")
        print(f"    形式: {r['format']}  日付: {r['date']}")
        print(f"    上映時刻: {r['showtimes']}")
        print()
