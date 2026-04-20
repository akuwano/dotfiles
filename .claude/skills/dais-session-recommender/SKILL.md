---
name: dais-session-recommender
description: |
  Databricks Data + AI Summit (DAIS) の最新アジェンダから、ユーザーのユースケース（業界・技術・ユースケース）に合ったセッションを推薦する。
  トリガー: "DAIS", "Data AI Summit", "サミット", "セッション推薦", "おすすめセッション", "agenda"
  使用場面: (1) 特定業界・事業領域に役立つDAISセッションを探す、(2) 特定技術（Lakebase, Genie, Unity Catalog等）の事例収集、(3) 出張/視聴優先度の判断
  データソース: https://www.databricks.com/dataaisummit/agenda （毎回直接取得して最新化）
---

# DAIS Session Recommender

Data + AI Summit の公式アジェンダページから全セッション情報を取得し、**Claude自身が内容を読んで** ユーザーのユースケースに沿って推薦するスキル。

## 設計原則

- **毎回 URL から直接取得**する（セッションは追加・変更される）
- **推薦判断（スコアリング、優先度、なぜおすすめ）は Claude がやる**。Pythonスクリプトは取得と整形だけ、機械的マッチングは書かない
  - キーワード一致で並べ替えるとニュアンスを取りこぼす（例: 同じ "fraud" でも対策側か被害報告かで価値が違う）
  - 登壇企業の業界ポジション・事例の規模感・ユーザーの組織段階など、文脈依存の判断は Claude が行う
- **デフォルト値なし**。業界・件数等は必ずユーザーにヒアリング
- **画面表示のみ**。ファイル出力はユーザーが明示依頼した時だけ

## データ取得の仕組み

`https://www.databricks.com/dataaisummit/agenda` のHTMLに、Drupalが `"sessions":[ ... ]` としてJSON配列を埋め込み。ページネーションはクライアントサイドJSのみ、1リクエストで全件取得できる。

各セッションのフィールド:

| フィールド | 内容 |
|---|---|
| `title` | タイトル |
| `body` | HTML形式の概要 |
| `speakers[]` | `{name, job_title, company, bio, ...}` |
| `alias` | セッション詳細URL（`/session/...`） |
| `duration` | 分 |
| `categories.type` | Breakout / Lightning Talk / Paid Training / Keynote |
| `categories.track` | Data Engineering & Streaming 等 |
| `categories.category` | Lakebase, Unity Catalog, AI/BI 等 |
| `categories.industry` | Financial Services 等 |
| `categories.level` | Beginner / Intermediate / Advanced |
| `categories.areasofinterest` | AI Agents, Data Applications 等 |

## 実行手順

### Step 1: ヒアリング（必須）

ユーザーが条件を指定していない限り、以下を聞く:

- **業界/事業領域**（金融、保険、小売、製造、ヘルスケア、メディア、公共、指定なし）
- **関心ユースケース**（不正検知、Customer360、リアルタイム分析、コスト最適化、規制対応、基盤移行、AIエージェント など）
- **関心技術**（Lakebase, Genie, Unity Catalog, Agent Bricks, Delta Sharing, Lakeflow 等）
- **件数**（Top 10 / Top 20 / Top 30 / 全件）
- **視聴者の立場**（CxO・アーキテクト・データエンジニア・アナリスト等 — 推薦観点が変わる）

1つだけ指定でも実行OK。曖昧な場合は1往復だけ深掘り質問する。

### Step 2: セッション取得

```bash
python3 scripts/fetch_sessions.py --format slim --output /tmp/dais_sessions.json
```

`--format slim` を使う（body を600字に切り詰め、Claudeが読み込む文脈サイズを抑制）。

さらに深い概要が必要なセッションだけ、**ピンポイントで** `--format full` で取り直してもよい。

### Step 3: Claude が読む＋判断する

Read tool で `/tmp/dais_sessions.json` を開き、168件の内容を把握する。その上で:

1. **フィルタリング**: ユーザーの業界・技術・ユースケースに明らかに無関係なセッションを除外
2. **スコアリング（内部）**: 以下を総合して優先度を判定（機械式ではなく、**読んで決める**）
   - 登壇企業が同業界のリーダーか（例: 金融ならNubank, Barclays, Mastercard）
   - 技術スタックがユーザー関心と一致するか
   - 事例の規模感・再現性（数字で語れているか、単なる意気込みか）
   - 抽象度（概念紹介か、実装手順まで踏み込んでいるか）
   - 視聴者の立場との噛み合わせ（CxO→戦略、エンジニア→実装詳細）
3. **優先度ラベル**: ⭐⭐⭐⭐⭐ 必見 / ⭐⭐⭐⭐ 強く推奨 / ⭐⭐⭐ 推奨 / ⭐⭐ 参考 / ⭐ 関連
4. **なぜおすすめを書く**: 必見（⭐5）は必ず。それ以下は要望に応じて
   - 機械的キーワード羅列はNG
   - 「なぜ**このユーザー**にこのセッションか」を1〜3文で書く
   - 事例ものは規模感・業界固有課題との対応、技術ものは典型的適用パターン

### Step 4: 画面表示

以下の構成で会話に直接出す（ファイル出力はしない）:

1. 選定基準（業界・技術・件数）を冒頭に1〜2行で明示
2. **必見セッション**: タイトル + 登壇 + なぜおすすめ
3. **優先度一覧表**: 優先度/タイトル/登壇者/トラック/短い一言
4. 末尾で「もっと絞る？」「別テーマで見る？」を提示

長すぎる時は必見と一覧だけ表示し、詳細は追加リクエストに応じる方針。

### Step 5: ファイル保存（依頼時のみ）

ユーザーが「ファイルに保存して」と言ったら、そのMarkdownを `.md` ファイルに書き出す。パスもユーザー確認。

## スクリプト

- `scripts/fetch_sessions.py`: agenda HTMLからセッション配列を抽出
  - `--format slim`（デフォルト、推奨）: 要点のみ、body 600字切り詰め
  - `--format full`: 全フィールド
  - `--format table`: 目視確認用
  - `--body-chars N`: body切り詰め長さ（0=無制限）

## よくある使い方

| ユーザー発話 | 動き |
|---|---|
| 「DAISで金融向けTop20」 | 業界=金融、件数=20で取得→読解→推薦 |
| 「Lakebase事例集めて」 | 全件取得→Lakebase関連を読解して抜粋 |
| 「データエンジニア向け」 | 立場=DE、Data Engineering & Streamingトラック中心に読解 |
| 「ファイル保存して」 | 直前の推薦結果を `.md` で保存 |

## 注意

- HTML構造変更に弱い。`"sessions":[` が見つからないエラーが出たらフォールバック（WebFetch で `?page=N` 巡回）
- **Claudeが読む前提**なので、CLIで完結する複雑なフィルタ/ソートは実装しない
- **デフォルト値で勝手に走らない**。ユーザーに必ず条件を確認
