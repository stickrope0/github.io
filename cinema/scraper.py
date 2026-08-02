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
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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


_HTML_VIEWER = '''\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>新宿映画館スケジュール</title>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0d0b14;--bg2:#17132a;--bg3:#1e1930;
  --accent:#b48ee0;--accent2:#8b5fcf;
  --text:#e0d8f0;--sub:#8a7aaa;--border:rgba(180,142,224,.18);
  --up:#5ec85e;--dn:#d47030;
}
@media(prefers-color-scheme:light){:root{
  --bg:#f4f2f9;--bg2:#ffffff;--bg3:#ede9f5;
  --accent:#7a4fbf;--accent2:#5a2fa0;
  --text:#1a1428;--sub:#6b5a8a;--border:rgba(120,80,180,.18);
}}
:root[data-theme="dark"]{--bg:#0d0b14;--bg2:#17132a;--bg3:#1e1930;--accent:#b48ee0;--accent2:#8b5fcf;--text:#e0d8f0;--sub:#8a7aaa;--border:rgba(180,142,224,.18)}
:root[data-theme="light"]{--bg:#f4f2f9;--bg2:#ffffff;--bg3:#ede9f5;--accent:#7a4fbf;--accent2:#5a2fa0;--text:#1a1428;--sub:#6b5a8a;--border:rgba(120,80,180,.18)}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;min-height:100vh;-webkit-text-size-adjust:100%}
#topbar{position:sticky;top:0;z-index:100;background:rgba(13,11,20,.92);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--border);padding:.55rem 1rem;display:flex;align-items:center;gap:.75rem;min-height:48px}
:root[data-theme="light"] #topbar{background:rgba(244,242,249,.92)}
@media(prefers-color-scheme:light){#topbar{background:rgba(244,242,249,.92)}}
#back-btn{display:none;flex-shrink:0;background:transparent;border:1px solid var(--border);color:var(--accent);border-radius:8px;padding:.28rem .75rem;cursor:pointer;font-size:.85rem;white-space:nowrap}
#back-btn:hover{background:var(--bg3)}
#back-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#topbar-title{font-size:.88rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;color:var(--sub);letter-spacing:.1em;text-transform:uppercase}
#app{max-width:960px;margin:0 auto;padding:1.2rem .9rem 4rem}
.poster-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(115px,1fr));gap:10px}
@media(min-width:480px){.poster-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}}
@media(min-width:960px){.poster-grid{grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}}
.poster-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:hidden;cursor:pointer;transition:transform .15s,box-shadow .15s}
.poster-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.4)}
.poster-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.poster-img-wrap{position:relative;aspect-ratio:2/3;overflow:hidden;background:var(--bg3)}
.poster-noimg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:.5rem;text-align:center;font-size:.72rem;font-weight:500;color:var(--sub);background:linear-gradient(135deg,var(--bg3) 0%,var(--bg2) 100%)}
.poster-img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.poster-overlay{position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,0,0,.72));padding:1.4rem .45rem .4rem;display:flex;justify-content:space-between;align-items:flex-end;pointer-events:none}
.poster-score{font-size:.8rem;font-weight:700;color:#fff;font-variant-numeric:tabular-nums;line-height:1}
.poster-sc{font-size:.63rem;color:rgba(255,255,255,.75);display:flex;align-items:center;gap:.2rem}
.poster-info{padding:.4rem .5rem .52rem}
.poster-title{font-size:.74rem;font-weight:500;line-height:1.3;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.poster-release{color:var(--sub);font-size:.66rem;margin-top:.22rem}
.badge{display:inline-block;padding:.1rem .42rem;border-radius:5px;font-size:.67rem;font-weight:700;letter-spacing:.02em}
.bg{background:rgba(100,200,100,.15);color:#5ec85e}
.bpg{background:rgba(240,190,60,.15);color:#c89020}
.br15{background:rgba(240,120,50,.15);color:#c87030}
.br18{background:rgba(220,60,60,.15);color:#c04040}
.bno{background:rgba(138,122,170,.15);color:var(--sub)}
.fmt{display:inline-block;padding:.09rem .38rem;border-radius:5px;font-size:.69rem;font-weight:600}
.fs{background:rgba(80,170,220,.15);color:#50a8d8}
.fd{background:rgba(150,90,220,.15);color:#a060d0}
.fi{background:rgba(230,170,50,.15);color:#c89020}
.f4{background:rgba(240,110,50,.15);color:#c06030}
.fsx{background:rgba(210,70,160,.15);color:#c040a0}
.fdb{background:rgba(70,130,220,.15);color:#4880d0}
.fo{background:rgba(138,122,170,.15);color:var(--sub)}
.star{color:#f0c050;font-size:.87rem;font-variant-numeric:tabular-nums}
:root[data-theme="light"] .star{color:#b07800}
@media(prefers-color-scheme:light){.star{color:#b07800}}
.delta-new{font-size:.65rem;font-weight:700;color:var(--up);padding:.07rem .28rem;background:rgba(94,200,94,.12);border-radius:4px}
.delta-up{font-size:.72rem;font-weight:700;color:var(--up)}
.delta-dn{font-size:.72rem;font-weight:700;color:var(--dn)}
.sc-wrap{display:flex;align-items:center;gap:.3rem;font-variant-numeric:tabular-nums;font-size:.82rem}
.detail-header{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;margin-bottom:1.3rem}
.detail-title{font-size:1.2rem;font-weight:600;margin-bottom:.55rem;line-height:1.35}
.detail-meta{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;font-size:.82rem;color:var(--sub)}
.date-section{margin-bottom:1.4rem}
.date-heading{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;color:var(--sub);margin-bottom:.6rem;padding-bottom:.3rem;border-bottom:1px solid var(--border)}
.theater-rows{display:flex;flex-direction:column;gap:.4rem}
.theater-row{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:.6rem .9rem;display:flex;flex-wrap:wrap;align-items:center;gap:.5rem}
.theater-name{font-size:.84rem;min-width:120px;flex-shrink:0}
.time-pills{display:flex;flex-wrap:wrap;gap:.25rem}
.time-pill{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:.16rem .48rem;font-size:.79rem;font-variant-numeric:tabular-nums}
.page-heading{font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);margin-bottom:.9rem}
.empty{color:var(--sub);text-align:center;padding:3rem;font-size:.9rem}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div id="topbar">
  <button id="back-btn" onclick="go('/')">&#8592; 一覧へ戻る</button>
  <span id="topbar-title">新宿 Cinema</span>
</div>
<div id="app"></div>
<script>
const RAW = DATA_PLACEHOLDER;
const PREV = PREV_PLACEHOLDER;

function isSat(d) { return new Date(d+'T00:00:00').getDay() === 6; }

function countST(data) {
  const m = {};
  for (const r of data) {
    if (!isSat(r.date)) continue;
    m[r.movie_id] = (m[r.movie_id]||0) + (r.showtimes||[]).length;
  }
  return m;
}
const PC = countST(PREV);

function buildMovies(raw) {
  const map = {};
  for (const r of raw) {
    if (!map[r.movie_id]) map[r.movie_id] = {
      id: r.movie_id, title: r.title, release_date: r.release_date,
      duration: r.duration, rating: r.rating,
      star: parseFloat(r.star)||0, sc: 0, poster: r.poster||''
    };
    if (isSat(r.date)) map[r.movie_id].sc += (r.showtimes||[]).length;
  }
  return Object.values(map).sort((a,b) => b.star - a.star);
}

function getSchedules(movieId) {
  const byDate = {};
  for (const r of RAW) {
    if (r.movie_id !== movieId) continue;
    if (!byDate[r.date]) byDate[r.date] = {};
    const key = r.theater_name + '||' + r.format;
    if (!byDate[r.date][key]) byDate[r.date][key] = {theater_name:r.theater_name, format:r.format, times:[]};
    byDate[r.date][key].times.push(...r.showtimes);
  }
  return Object.entries(byDate).sort(([a],[b]) => a.localeCompare(b))
    .map(([date,ents]) => ({date, entries:Object.values(ents).sort((a,b) =>
      a.theater_name.localeCompare(b.theater_name)||a.format.localeCompare(b.format))}));
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtRelease(s) {
  const m = String(s).match(/(\d+)月(\d+)日/);
  return m ? m[1]+'/'+m[2] : s;
}
function ratingBadge(r) {
  if (!r) return '';
  const c = /^G$/i.test(r)?'bg':/PG12/i.test(r)?'bpg':/R15/i.test(r)?'br15':/R18/i.test(r)?'br18':'bno';
  return `<span class="badge ${c}">${esc(r)}</span>`;
}
function fmtBadge(f) {
  const c = /字幕/.test(f)?'fs':/吹替/.test(f)?'fd':/IMAX/i.test(f)?'fi':/4DX/i.test(f)?'f4':/ScreenX/i.test(f)?'fsx':/Dolby|BESTIA/i.test(f)?'fdb':'fo';
  return `<span class="fmt ${c}">${esc(f)}</span>`;
}
function fmtDate(d) {
  const dt = new Date(d+'T00:00:00');
  const w = ['日','月','火','水','木','金','土'];
  return `${dt.getMonth()+1}/${dt.getDate()}（${w[dt.getDay()]}）`;
}
function starHtml(s) {
  if (!s) return '<span style="color:var(--sub)">—</span>';
  return `<span class="star">${s.toFixed(1)}</span>`;
}
function deltaHtml(id, cur) {
  if (!PREV.length) return '';
  const prev = PC[id]||0;
  if (!prev) return '<span class="delta-new">NEW</span>';
  const d = cur - prev;
  if (!d) return '';
  return `<span class="delta-${d>0?'up':'dn'}">${d>0?'↑':'↓'}${Math.abs(d)}</span>`;
}

const MOVIES = buildMovies(RAW);

function renderList() {
  document.getElementById('back-btn').style.display = 'none';
  document.getElementById('topbar-title').textContent = '新宿 Cinema';
  const cards = MOVIES.map(m => {
    const imgEl = m.poster ? `<img class="poster-img" src="${esc(m.poster)}" referrerpolicy="no-referrer" alt="${esc(m.title)}" loading="lazy">` : '';
    const scoreEl = m.star ? `<span class="poster-score">${m.star.toFixed(1)}</span>` : '';
    const scEl = m.sc ? `<span class="poster-sc">${m.sc}回${deltaHtml(m.id,m.sc)}</span>` : '';
    return `<div class="poster-card" tabindex="0" onclick="go('movie/${esc(m.id)}')" onkeydown="if(event.key==='Enter')go('movie/${esc(m.id)}')">
      <div class="poster-img-wrap"><div class="poster-noimg">${esc(m.title.slice(0,8))}</div>${imgEl}<div class="poster-overlay">${scoreEl}${scEl}</div></div>
      <div class="poster-info"><div class="poster-title">${esc(m.title)}</div><div class="poster-release">${esc(fmtRelease(m.release_date))}</div></div>
    </div>`;
  }).join('');
  document.getElementById('app').innerHTML =
    `<p class="page-heading">上映作品一覧 — ${MOVIES.length} 作品</p>` +
    `<div class="poster-grid">${cards}</div>`;
}

function renderDetail(movieId) {
  const movie = MOVIES.find(m => m.id === movieId);
  if (!movie) { document.getElementById('app').innerHTML = '<p class="empty">作品が見つかりません</p>'; return; }
  document.getElementById('back-btn').style.display = '';
  document.getElementById('topbar-title').textContent = movie.title;
  const schedules = getSchedules(movieId);
  const blocks = schedules.map(({date, entries}) => {
    const rows = entries.map(e => `
      <div class="theater-row">
        <span class="theater-name">${esc(e.theater_name)}</span>
        ${fmtBadge(e.format)}
        <div class="time-pills">${e.times.map(t => `<span class="time-pill">${esc(t)}</span>`).join('')}</div>
      </div>`).join('');
    return `<div class="date-section"><div class="date-heading">${fmtDate(date)}</div><div class="theater-rows">${rows}</div></div>`;
  }).join('');
  document.getElementById('app').innerHTML =
    `<div class="detail-header">` +
    `<div class="detail-title">${esc(movie.title)}</div>` +
    `<div class="detail-meta"><span>${esc(fmtRelease(movie.release_date))}</span><span>${esc(movie.duration)}</span>${ratingBadge(movie.rating)}${starHtml(movie.star)}</div>` +
    `</div>` +
    (blocks || '<p class="empty">スケジュールデータがありません</p>');
}

function go(path) { location.hash = '/' + path; }

function router() {
  const hash = location.hash.replace(/^#\/?/, '');
  const m = hash.match(/^movie\/(\d+)$/);
  if (m) renderDetail(m[1]);
  else renderList();
}

window.addEventListener('hashchange', router);
router();
</script>
</body>
</html>
'''


def save_html(rows, path, prev_rows=None):
    data_json = json.dumps(rows, ensure_ascii=False)
    data_json = data_json.replace("</", "<\\/")
    prev_json = json.dumps(prev_rows or [], ensure_ascii=False)
    prev_json = prev_json.replace("</", "<\\/")
    html = _HTML_VIEWER.replace("DATA_PLACEHOLDER", data_json)
    html = html.replace("PREV_PLACEHOLDER", prev_json)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


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

    save_json(all_rows, json_path)
    save_csv(all_rows, csv_path)
    save_json(all_rows, latest_path)
    save_html(all_rows, html_path, prev_rows)

    print(f"\n完了: {len(all_rows)} 行")
    print(f"  JSON : {json_path}")
    print(f"  CSV  : {csv_path}")
    print(f"  最新 : {latest_path}")
    print(f"  HTML : {html_path}")


if __name__ == "__main__":
    main()
