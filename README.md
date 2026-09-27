# 新宿映画館スケジュール自動取得

新宿エリアを中心とした10館の上映スケジュールを映画.comから週次で自動取得し、JSON/CSVに保存します。

## 対象映画館

| 館名 | 劇場ID |
|------|--------|
| 新宿ピカデリー | 3017 |
| テアトル新宿 | 3022 |
| シネマート新宿 | 3020 |
| kino cinema新宿 | 3322 |
| 新宿武蔵野館 | 3026 |
| K's cinema | 3018 |
| 新宿バルト9 | 3016 |
| TOHOシネマズ 新宿 | 3263 |
| 109シネマズプレミアム新宿 | 3318 |
| アップリンク吉祥寺 | 3285 |

## セットアップ

```bash
cd cinema
pip install -r requirements.txt
```

## 実行

```bash
cd cinema
python scraper.py
```

出力先: `cinema/out/`
- `schedule_YYYYMMDD_HHMMSS.json` — 実行時刻付きの履歴ファイル
- `schedule_YYYYMMDD_HHMMSS.csv`  — 同上（Excel等で開けるUTF-8 BOM付き）
- `schedule_latest.json`          — 最新実行結果（上書き）

## 出力フィールド

| フィールド | 説明 |
|------------|------|
| theater_id | 映画.com の劇場ID |
| theater_name | 館名 |
| movie_id | 映画.com の作品ID |
| title | 作品タイトル |
| release_date | 公開日（例: 7月10日公開） |
| duration | 上映時間（例: 94分） |
| rating | レーティング（例: R15+） |
| star | 映画.com 評価 |
| format | 上映形式（字幕/吹替/IMAX/通常 等） |
| date | 上映日（YYYY-MM-DD） |
| showtimes | 上映時刻リスト（JSON配列 / CSV ではカンマ区切り） |

## 自動実行（GitHub Actions）

`.github/workflows/scrape.yml` により毎週火曜 19:00 JST（UTC 10:00）に自動実行されます。

**必要な設定:**
リポジトリの Settings > Actions > General > Workflow permissions で
**"Read and write permissions"** を有効にしてください（結果のコミット・プッシュに必要）。

手動実行: GitHub の Actions タブ → "新宿映画館スケジュール取得" → Run workflow

## GitHub Pages

`.github/workflows/pages.yml` により `master` ブランチへの変更を自動でGitHub Pagesへ公開します。
初回のみ、リポジトリの Settings > Pages > Build and deployment で
**Source: GitHub Actions** を選択してください。

公開URL:
`https://stickrope0.github.io/github.io/`

スケジュール閲覧ページ:
`https://stickrope0.github.io/github.io/cinema/out/viewer.html`

グラフページ（上映回数の推移・ランキング・評価との散布図）:
`https://stickrope0.github.io/github.io/cinema/out/stats.html`

どちらも `scraper.py` の実行時に `cinema/viewer_template.html` / `cinema/stats_template.html` から生成されます。
作品の check 状態はブラウザ内（localStorage）に保存され、2ページで共有されます。

## 上映終了の判定

`cinema/end_judge.py` が取得履歴から作品ごとに上映終了の近さを判定し、ビューアにバッジ（終了濃厚／終了注意）を表示します。
作品は上映の型で分けて判定します。

| 型 | 判定方法 | 警告の条件 |
|----|----------|------------|
| リバイバル型 | 作品IDが最新より1万以上小さい、または公開から半年以上 | 上映2週目以降かつ（公開8週以上／各館の最終公開日に上映なし／週2日以下／朝だけ・夜だけ／1日平均0.5回以下）→ 終了濃厚 |
| 限定型 | これまで1日最大1回の上映 | 2週目以降かつ朝だけ・夜だけ → 終了濃厚、各館の最終公開日に上映なしかつ1日平均0.5回以下 → 終了注意 |
| 通常型 | 上記以外 | 1日1回以下かつ（週2日以下、または朝だけ・夜だけでピークの25%以下）→ 終了注意 |

条件は2026年7〜9月の取得データで、誤検知を減らす方針で決めました（的中率79%、終了作品の事前警告36%、継続作品への誤警告4%）。
毎回の判定は `cinema/out/end_judgments.json` に記録され、次の取得で実際に終了したかを照合します。結果はグラフページの「上映終了の判定の実績」に表示されます。

## 注意事項

- **個人利用前提**: 本スクリプトは個人的な情報収集を目的としています
- **利用規約の確認**: 映画.com の[利用規約](https://eiga.com/help/terms/)および [robots.txt](https://eiga.com/robots.txt) を事前に確認し、遵守してください
- **アクセス頻度**: リクエスト間に2秒のスリープを設けています。サーバーへの過度な負荷を避けてください
- **データの取り扱い**: 取得したデータの二次配布や商用利用は行わないでください
