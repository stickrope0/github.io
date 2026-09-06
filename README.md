# 新宿映画館スケジュール自動取得

新宿エリア9館の上映スケジュールを映画.comから週次で自動取得し、JSON/CSVに保存します。

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

## 注意事項

- **個人利用前提**: 本スクリプトは個人的な情報収集を目的としています
- **利用規約の確認**: 映画.com の[利用規約](https://eiga.com/help/terms/)および [robots.txt](https://eiga.com/robots.txt) を事前に確認し、遵守してください
- **アクセス頻度**: リクエスト間に2秒のスリープを設けています。サーバーへの過度な負荷を避けてください
- **データの取り扱い**: 取得したデータの二次配布や商用利用は行わないでください
