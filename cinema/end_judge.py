"""
上映終了の判定と、その精度の検証。

作品を上映の「型」に分け、型ごとに的中率の高いサインだけで警告する。
  - リバイバル型: 映画.com の作品IDが最新より 1万以上小さい（登録から約4年以上）か、公開から半年以上
  - 限定型:       これまで 1日最大1回しか上映していない
  - 通常型:       上記以外（公開当初は 1日2回以上上映していた）
警告は「終了濃厚(high)」と「注意(watch)」の2段階。条件は 2026年7〜9月の取得データで検証した。

検証のため、毎回の判定を end_judgments.json に記録し、次の取得で実際に終わったかを照合する。
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

RUN_FILE = re.compile(r"schedule_\d{8}_\d{6}\.json$")
SAME_RUN_DAYS = 3   # 上映開始日がこの日数以内の取得は同じ週とみなす
NEXT_RUN_DAYS = 9   # 次の取得までの間隔がこれを超えたら「翌週」として比べない
REVIVAL_ID_GAP = 10000
REVIVAL_AGE_WEEKS = 26


# ── 取得履歴 ──

def _run_of(rows):
    dates = sorted({r["date"] for r in rows})
    return {"start": dates[0], "end": dates[-1], "days": len(dates), "rows": rows}


def load_runs(out_dir, exclude_start=None):
    """取得ファイルを週ごとに集約して古い順に返す（同じ週は行数の多い方を採用）。
    exclude_start を渡すと、その開始日と同じ週の取得は除く（今回の取得と重複させないため）。"""
    runs = []
    for p in sorted(Path(out_dir).glob("schedule_*.json")):
        if not RUN_FILE.match(p.name):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            continue
        if rows:
            runs.append(_run_of(rows))
    runs.sort(key=lambda r: r["start"])
    if exclude_start:
        runs = [r for r in runs if not _same_week(r["start"], exclude_start)]
    kept = []
    for r in runs:
        if kept and _same_week(r["start"], kept[-1]["start"]):
            if len(r["rows"]) >= len(kept[-1]["rows"]):
                kept[-1] = r
            continue
        kept.append(r)
    return kept


def _days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _same_week(a, b):
    return abs(_days_between(a, b)) <= SAME_RUN_DAYS


def _summarize(run):
    """作品ごとの週の集計"""
    out = {}
    for x in run["rows"]:
        m = out.setdefault(x["movie_id"], {
            "title": x["title"], "release": x.get("release_date", ""),
            "shows": 0, "byday": {}, "theaters": set(), "early": 0, "late": 0,
        })
        times = x.get("showtimes") or []
        m["shows"] += len(times)
        m["byday"][x["date"]] = m["byday"].get(x["date"], 0) + len(times)
        m["theaters"].add(x["theater_name"])
        for t in times:
            h = int(t.split(":")[0])
            m["early"] += h < 11
            m["late"] += h >= 20
    return out


def _release_date(text, ref):
    """「9月4日公開」「2017年9月1日公開」から公開日を求める（年なしは ref に近い年と解釈）"""
    m = re.search(r"(\d{4})年(\d+)月(\d+)日", text or "")
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d+)月(\d+)日", text or "")
    if not m:
        return None
    rel = date(ref.year, int(m[1]), int(m[2]))
    if rel > ref and (rel - ref).days > 60:
        rel = date(ref.year - 1, int(m[1]), int(m[2]))
    return rel


# ── 判定 ──

def judge(rows, out_dir):
    """今回の取得 rows の作品ごとに、型・警告・理由・確認できている最終上映を返す。"""
    if not rows:
        return {}
    cur = _run_of(rows)
    past = [r for r in load_runs(out_dir, exclude_start=cur["start"]) if r["start"] < cur["start"]]
    runs = past + [cur]
    weekly = [_summarize(r) for r in runs]
    now = weekly[-1]
    prev = weekly[-2] if len(runs) >= 2 and _days_between(runs[-2]["start"], cur["start"]) <= NEXT_RUN_DAYS else {}
    start = date.fromisoformat(cur["start"])
    max_id = max(int(x["movie_id"]) for x in rows if str(x["movie_id"]).isdigit())

    # 劇場ごとの「公開しているスケジュールの最終日」
    theater_last = {}
    for x in rows:
        theater_last[x["theater_name"]] = max(theater_last.get(x["theater_name"], ""), x["date"])

    # 確認できている最終上映（日時と劇場）。時刻は "9:05" 形式なので桁をそろえて比べる
    last_show = {}
    for x in rows:
        for t in x.get("showtimes") or []:
            key = (x["date"], t.zfill(5))
            if x["movie_id"] not in last_show or key > last_show[x["movie_id"]]["key"]:
                last_show[x["movie_id"]] = {"key": key, "date": x["date"], "time": t, "theater": x["theater_name"]}

    result = {}
    for mid, m in now.items():
        hist = [w[mid] for w in weekly if mid in w]
        peak_maxday = max(max(h["byday"].values()) for h in hist)
        peak_avg = max(h["shows"] / r["days"] for w, r in zip(weekly, runs) if mid in w for h in [w[mid]])
        run_weeks = 0
        for w in reversed(weekly):
            if mid not in w:
                break
            run_weeks += 1
        rel = _release_date(m["release"], start)
        age_weeks = (start - rel).days / 7 if rel else None

        avg = m["shows"] / cur["days"]
        days_shown = sum(1 for v in m["byday"].values() if v)
        on_last = sum(
            len(x.get("showtimes") or []) for x in rows
            if x["movie_id"] == mid and x["date"] == theater_last[x["theater_name"]]
        )
        f = {
            "not_last": on_last == 0,
            "one_a_day": max(m["byday"].values()) <= 1,
            "avg_half": avg <= 0.5,
            "peak_quarter": peak_avg > 0 and avg / peak_avg <= 0.25,
            "early_or_late": m["shows"] > 0 and (m["early"] == m["shows"] or m["late"] == m["shows"]),
            "two_days": days_shown <= 2,
            "second_week": run_weeks >= 2,
            "age8": age_weeks is not None and age_weeks >= 8,
        }
        revival = (str(mid).isdigit() and int(mid) < max_id - REVIVAL_ID_GAP) or \
                  (age_weeks is not None and age_weeks >= REVIVAL_AGE_WEEKS)
        kind = "revival" if revival else ("limited" if peak_maxday <= 1 else "regular")
        level, reasons = _level(kind, f, m)

        ls = last_show.get(mid)
        result[mid] = {
            "type": kind, "level": level, "reasons": reasons,
            "last_show": {k: ls[k] for k in ("date", "time", "theater")} if ls else None,
            "theaters": sorted(m["theaters"]),
            "title": m["title"],
        }
    return result


REASON_TEXT = {
    "not_last": "各館の最終公開日に上映なし",
    "avg_half": "1日平均0.5回以下",
    "early_or_late": "朝だけ・夜だけの上映",
    "two_days": "週2日以下の上映",
    "second_week": "上映2週目以降",
    "age8": "公開から8週以上",
    "one_a_day": "1日1回以下",
    "peak_quarter": "ピーク時の25%以下",
}


def _level(kind, f, m):
    """型ごとの警告レベルと理由。的中率を優先し、検証で精度が出なかった条件では警告しない。"""
    def hit(*keys):
        return [REASON_TEXT[k] for k in keys if f[k]]

    if kind == "revival":
        extra = hit("age8", "not_last", "two_days", "early_or_late", "avg_half")
        if f["second_week"] and extra:
            return "high", [REASON_TEXT["second_week"]] + extra
        return None, []
    if kind == "limited":
        if f["second_week"] and f["early_or_late"]:
            return "high", hit("second_week", "early_or_late")
        if f["not_last"] and f["avg_half"]:
            return "watch", hit("not_last", "avg_half")
        return None, []
    # 通常型：的中率が 65% を超える条件がなかったため「注意」のみ
    if f["one_a_day"] and (f["two_days"] or (f["early_or_late"] and f["peak_quarter"])):
        return "watch", hit("one_a_day", "two_days", "early_or_late", "peak_quarter")
    return None, []


# ── 精度の検証 ──

def update_log(log_path, rows, status):
    """前回の判定を今回の取得結果と照合して evaluations に追記し、今回の判定を pending に保存する。"""
    log_path = Path(log_path)
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        log = {"pending": None, "evaluations": []}
    if not rows:
        return log
    cur = _run_of(rows)
    pending = log.get("pending")

    if pending and _same_week(pending["start"], cur["start"]):
        pass  # 同じ週の取り直し：照合せず、判定を差し替える
    elif pending and _days_between(pending["start"], cur["start"]) <= NEXT_RUN_DAYS:
        log["evaluations"].append(_evaluate(pending, rows))
    elif pending:
        log["evaluations"].append({"start": pending["start"], "next_start": cur["start"],
                                   "skipped": "次の取得まで間が空いたため照合できません"})

    log["pending"] = {
        "start": cur["start"], "end": cur["end"],
        "generated": datetime.now().isoformat(timespec="seconds"),
        "theaters": sorted({x["theater_name"] for x in rows}),
        "movies": {mid: {"title": s["title"], "type": s["type"], "level": s["level"], "theaters": s["theaters"]}
                   for mid, s in status.items()},
    }
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return log


def _evaluate(pending, rows):
    # 取得した劇場が変わっても誤って「終了」としないよう、両方の回で取得できた劇場だけで比べる
    common = set(pending["theaters"]) & {x["theater_name"] for x in rows}
    shown_now = {x["movie_id"] for x in rows if x["theater_name"] in common}
    items = []
    for mid, p in pending["movies"].items():
        if not set(p["theaters"]) & common:
            continue
        items.append({"id": mid, "title": p["title"], "type": p["type"], "level": p["level"],
                      "ended": mid not in shown_now})
    return {
        "start": pending["start"],
        "next_start": _run_of(rows)["start"],
        "movies": len(items),
        "ended": sum(i["ended"] for i in items),
        # 集計しやすいよう、警告した作品と、警告なしで終わった作品（見逃し）だけを残す
        "alerts": [i for i in items if i["level"]],
        "missed": [i for i in items if i["ended"] and not i["level"]],
    }
