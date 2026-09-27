"""
映画.com 新宿エリア 上映スケジュール スクレイパー

対象: https://eiga.com/theater/13/130201/
出力: out/schedule_YYYYMMDD_HHMMSS.json / .csv
      out/schedule_latest.json
"""

import csv
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import end_judge

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

BASE_URL = "https://eiga.com"
LIST_URL = "https://eiga.com/theater/13/130201/"
EXTRA_THEATERS = [
    {
        "theater_id": "3285",
        "name": "アップリンク吉祥寺",
        "url": f"{BASE_URL}/theater/13/130809/3285/",
    },
]
SLEEP_SEC = 2
OUT_DIR = Path("out")

CSV_FIELDS = [
    "theater_id", "theater_name",
    "movie_id", "title", "release_date", "duration", "rating", "star", "poster",
    "format", "date", "showtimes",
]


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return BeautifulSoup(resp.text, "html.parser")


def get_theaters():
    soup = fetch(LIST_URL)
    seen = set()
    theaters = []
    for a in soup.select("ul.theater-tile a[href]"):
        href = a["href"]
        m = re.match(r"/theater/\d+/\d+/(\d+)/", href)
        if not m:
            continue
        tid = m.group(1)
        name = a.get_text(strip=True)
        if tid in seen or not name:
            continue
        seen.add(tid)
        theaters.append({"theater_id": tid, "name": name, "url": BASE_URL + href})
    for theater in EXTRA_THEATERS:
        if theater["theater_id"] not in seen:
            theaters.append(theater)
    return theaters


def _movie_info(section):
    title_a = section.select_one("h2.title-xlarge a")
    title = title_a.get_text(strip=True) if title_a else section.get("data-title", "")
    href = title_a["href"] if title_a else ""
    m = re.search(r"/movie/(\d+)/", href)
    movie_id = m.group(1) if m else ""

    data_spans = section.select("p.data span")
    release_date = data_spans[0].get_text(strip=True) if len(data_spans) > 0 else ""
    duration     = data_spans[1].get_text(strip=True) if len(data_spans) > 1 else ""
    rating       = data_spans[2].get_text(strip=True) if len(data_spans) > 2 else ""

    star_el = section.select_one("span[class*='rating-star']")
    star = star_el.get_text(strip=True) if star_el else ""

    return {"movie_id": movie_id, "title": title, "release_date": release_date,
            "duration": duration, "rating": rating, "star": star, "poster": ""}


def _parse_time_cell(td):
    # a.btn: TOHOシネマズ等チケット購入リンク
    # span.btn: 売切・時間外
    # a.official: テアトル新宿・シネマート等独立系
    times = []
    for btn in td.select("span.btn, a.btn, a.official"):
        small = btn.find("small")
        if small:
            small.decompose()
        t = btn.get_text(strip=True)
        # 「16:20〜18:07」形式から開始時刻のみ残す
        t = re.sub(r"〜\d{1,2}:\d{2}$", "", t).strip()
        if t:
            times.append(t)
    return times


def scrape_theater(theater):
    soup = fetch(theater["url"])
    rows = []
    for section in soup.select("section[id]"):
        sec_id = section.get("id", "")
        if not re.match(r"^m\d+$", sec_id):
            continue
        movie = _movie_info(section)
        for sched_div in section.select("div.movie-schedule"):
            fmt_span = sched_div.select_one("div.movie-type span")
            fmt_text = fmt_span.get_text(strip=True) if fmt_span else "通常"
            table = sched_div.select_one("table.weekly-schedule")
            if not table:
                continue
            for td in table.select("td[data-date]"):
                date_raw = td.get("data-date", "")
                try:
                    date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
                except Exception:
                    date_str = date_raw
                times = _parse_time_cell(td)
                if not times:
                    continue
                rows.append({
                    "theater_id": theater["theater_id"],
                    "theater_name": theater["name"],
                    **movie,
                    "format": fmt_text,
                    "date": date_str,
                    "showtimes": times,
                })
    return rows


def save_json(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def save_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {**row, "showtimes": ",".join(row.get("showtimes", []))}
            writer.writerow(flat)


def fetch_posters(movie_ids):
    posters = {}
    total = len(movie_ids)
    for i, movie_id in enumerate(movie_ids, 1):
        try:
            soup = fetch(f"{BASE_URL}/movie/{movie_id}/photo/")
            img = soup.select_one(f"img[src*='/movie/{movie_id}/photo/']")
            if img:
                src = img["src"]
                m = re.match(r"(https://media\.eiga\.com/images/movie/\d+/photo/[0-9a-f]+)\.jpg$", src)
                posters[movie_id] = (m.group(1) + "/320.jpg") if m else src
            print(f"  poster [{i}/{total}] {movie_id}: {'OK' if movie_id in posters else 'not found'}")
        except Exception as e:
            print(f"  poster [{i}/{total}] {movie_id}: error - {e}")
        if i < total:
            time.sleep(1)
    return posters


def _prev_movie_static(prev_rows):
    """前回取得済みの映画ごとの静的情報(公開日/上映時間/レーティング/ポスター)。
    これらは変化しない前提で、続映作品は再取得せず流用する。
    """
    info = {}
    for r in prev_rows:
        mid = r.get("movie_id")
        if mid and mid not in info:
            info[mid] = {
                "release_date": r.get("release_date", ""),
                "duration": r.get("duration", ""),
                "rating": r.get("rating", ""),
                "poster": r.get("poster", ""),
            }
    return info


def _load_prev(out_dir):
    pat = re.compile(r"schedule_(\d{8}_\d{6})\.json")
    candidates = []
    for p in out_dir.glob("schedule_*.json"):
        m = pat.match(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        return []
    candidates.sort(key=lambda x: x[0], reverse=True)
    try:
        with open(candidates[0][1], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


TEMPLATE_DIR = Path(__file__).parent
VIEWER_TEMPLATE = TEMPLATE_DIR / "viewer_template.html"
STATS_TEMPLATE = TEMPLATE_DIR / "stats_template.html"


def _embed_json(data):
    """<script> 内に埋め込めるよう </ をエスケープした JSON 文字列。"""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _render(template_path, out_path, **placeholders):
    html = template_path.read_text(encoding="utf-8")
    # /*@include ファイル名*/ を同じフォルダのファイルの中身で置き換える（ページ間で共通の JS）
    html = re.sub(
        r"/\*@include ([\w.-]+)\*/",
        lambda m: (TEMPLATE_DIR / m.group(1)).read_text(encoding="utf-8"),
        html,
    )
    for key, data in placeholders.items():
        html = html.replace(f"{key}_PLACEHOLDER", _embed_json(data))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def save_html(rows, path, prev_rows=None, status=None):
    _render(VIEWER_TEMPLATE, path, DATA=rows, PREV=prev_rows or [], STATUS=status or {})


def build_history(out_dir):
    """取得履歴から、作品ごとの「1日あたり平均上映回数」の推移を作る。
    上映開始日が3日以内に重なる取得回は1つにまとめ、行数の多い方を採用する。
    """
    kept = end_judge.load_runs(out_dir)
    points = [
        {"date": r["start"], "theaters": len({x["theater_name"] for x in r["rows"]})}
        for r in kept
    ]
    movies = {}
    for i, r in enumerate(kept):
        per = {}
        for x in r["rows"]:
            mid = x["movie_id"]
            per[mid] = per.get(mid, 0) + len(x.get("showtimes") or [])
            if mid not in movies:
                movies[mid] = {"title": x["title"], "vals": [0.0] * len(kept)}
        for mid, n in per.items():
            movies[mid]["vals"][i] = round(n / r["days"], 2)
    return {"points": points, "movies": movies}


def save_stats_html(rows, path, prev_rows=None, history=None, evaluations=None):
    _render(STATS_TEMPLATE, path, DATA=rows, PREV=prev_rows or [],
            HIST=history or {"points": [], "movies": {}}, EVAL=evaluations or [])


def main():
    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prev_rows = _load_prev(OUT_DIR)

    print("劇場一覧を取得中...")
    theaters = get_theaters()
    print(f"  {len(theaters)} 館を取得\n")

    all_rows = []
    for i, theater in enumerate(theaters, 1):
        print(f"[{i}/{len(theaters)}] {theater['name']} を取得中...")
        try:
            rows = scrape_theater(theater)
            all_rows.extend(rows)
            movies = len({r["movie_id"] for r in rows})
            print(f"  -> {movies} 作品 / {len(rows)} スケジュール行")
        except requests.HTTPError as e:
            print(f"  -> HTTP エラー: {e}")
        except Exception as e:
            print(f"  -> エラー: {e}")
        if i < len(theaters):
            time.sleep(SLEEP_SEC)

    prev_static = _prev_movie_static(prev_rows)

    unique_ids = list({r["movie_id"] for r in all_rows if r.get("movie_id")})
    new_ids = [mid for mid in unique_ids if mid not in prev_static]
    print(f"\nポスター画像を取得中 (新規 {len(new_ids)} 作品 / 続映 {len(unique_ids) - len(new_ids)} 作品はスキップ)...")
    poster_map = fetch_posters(new_ids)
    for row in all_rows:
        mid = row["movie_id"]
        cached = prev_static.get(mid)
        if cached:
            row["release_date"] = cached["release_date"]
            row["duration"] = cached["duration"]
            row["rating"] = cached["rating"]
            row["poster"] = cached["poster"]
        else:
            row["poster"] = poster_map.get(mid, "")

    json_path   = OUT_DIR / f"schedule_{ts}.json"
    csv_path    = OUT_DIR / f"schedule_{ts}.csv"
    latest_path = OUT_DIR / "schedule_latest.json"
    html_path   = OUT_DIR / "viewer.html"
    stats_path  = OUT_DIR / "stats.html"
    judge_path  = OUT_DIR / "end_judgments.json"

    save_json(all_rows, json_path)
    save_csv(all_rows, csv_path)
    save_json(all_rows, latest_path)
    # 上映終了の判定と、前回の判定の答え合わせ
    status = end_judge.judge(all_rows, OUT_DIR)
    judge_log = end_judge.update_log(judge_path, all_rows, status)
    save_html(all_rows, html_path, prev_rows, status)
    save_stats_html(all_rows, stats_path, prev_rows, build_history(OUT_DIR), judge_log["evaluations"])

    print(f"\n完了: {len(all_rows)} 行")
    print(f"  JSON : {json_path}")
    print(f"  CSV  : {csv_path}")
    print(f"  最新 : {latest_path}")
    print(f"  HTML : {html_path}")
    print(f"  グラフ: {stats_path}")
    alerts = sum(1 for v in status.values() if v["level"])
    print(f"  終了判定: {alerts} 作品に警告（記録: {judge_path}）")


if __name__ == "__main__":
    main()
