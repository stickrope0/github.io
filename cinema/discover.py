"""
HTML構造調査スクリプト
実際のHTMLを出力してパーサーセレクタを確認する
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

BASE_URL = "https://eiga.com"
LIST_URL = "https://eiga.com/theater/13/130201/"
SAMPLE_THEATER_URL = "https://eiga.com/theater/13/130201/3263/"  # TOHOシネマズ新宿


def dump_theater_list():
    print("=" * 60)
    print("【劇場一覧ページ】", LIST_URL)
    print("=" * 60)
    r = requests.get(LIST_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    # 劇場リンクを探す: /theater/13/130201/XXXX/ パターン
    links = soup.find_all("a", href=True)
    theater_links = [
        a for a in links
        if "/theater/13/130201/" in a["href"]
        and a["href"].rstrip("/").split("/")[-1].isdigit()
    ]

    print(f"\n見つかった劇場リンク数: {len(theater_links)}")
    for a in theater_links:
        print(f"  {a.get_text(strip=True)!r:30s}  href={a['href']}")

    # 劇場名を含む親要素を確認
    if theater_links:
        print("\n--- 最初のリンクの周辺HTML ---")
        parent = theater_links[0].parent
        for _ in range(3):
            if parent:
                print(f"tag={parent.name}, class={parent.get('class')}, id={parent.get('id')}")
                parent = parent.parent


def dump_theater_schedule():
    print("\n" + "=" * 60)
    print("【劇場詳細ページ】", SAMPLE_THEATER_URL)
    print("=" * 60)
    r = requests.get(SAMPLE_THEATER_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    # body直下の主要セクションを把握
    print("\n--- body直下の主要タグ (depth=1,2) ---")
    body = soup.body
    if body:
        for child in body.children:
            if hasattr(child, "name") and child.name:
                print(f"  <{child.name} class={child.get('class')} id={child.get('id')}>")

    # h2タグを全て列挙（映画タイトルの候補）
    print("\n--- h2タグ一覧 ---")
    for h2 in soup.find_all("h2"):
        a = h2.find("a")
        print(f"  class={h2.get('class')} | text={h2.get_text(strip=True)[:50]!r} | link={a['href'] if a else None}")

    # /movie/ リンクを持つ要素を探す
    print("\n--- /movie/ リンクの周辺構造（最初の3件）---")
    movie_links = [a for a in soup.find_all("a", href=True) if "/movie/" in a["href"] and a.get_text(strip=True)]
    for a in movie_links[:3]:
        print(f"\n  リンク: {a['href']} | テキスト: {a.get_text(strip=True)!r}")
        # 親→祖先を3段階確認
        p = a.parent
        for depth in range(5):
            if p and p.name:
                print(f"    depth={depth} tag=<{p.name}> class={p.get('class')} id={p.get('id')}")
                p = p.parent

    # 上映スケジュール部分のHTML断片を直接出力（先頭3000文字）
    print("\n--- ページHTML断片（先頭部分を除いたmain/article/section等）---")
    for tag_name in ["main", "article", "section", "div"]:
        el = soup.find(tag_name, id=True)
        if el:
            print(f"\n最初の id 付き <{tag_name}> id={el.get('id')} class={el.get('class')}")
            print(str(el)[:2000])
            break

    # 日付・時刻パターンを探す（「月/日（曜）」形式）
    import re
    print("\n--- 日付・時刻パターンを含むテキストノード（最初の20件）---")
    date_pattern = re.compile(r"\d+/\d+（[日月火水木金土]）")
    time_pattern = re.compile(r"\d{1,2}:\d{2}")
    found = 0
    for tag in soup.find_all(string=date_pattern):
        el = tag.parent
        print(f"  tag=<{el.name}> class={el.get('class')} | {str(tag).strip()[:80]!r}")
        found += 1
        if found >= 20:
            break

    print("\n--- 上映形式（字幕/吹替/IMAX）を含む要素（最初の10件）---")
    format_pattern = re.compile(r"字幕|吹替|IMAX|4DX|ScreenX|MX4D|Dolby|BESTIA")
    found = 0
    for tag in soup.find_all(string=format_pattern):
        el = tag.parent
        print(f"  tag=<{el.name}> class={el.get('class')} id={el.get('id')} | {str(tag).strip()[:50]!r}")
        found += 1
        if found >= 10:
            break


if __name__ == "__main__":
    dump_theater_list()
    dump_theater_schedule()
    print("\n調査完了")
