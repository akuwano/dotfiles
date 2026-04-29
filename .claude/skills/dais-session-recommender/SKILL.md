---
name: dais-session-recommender
description: |
  Databricks Data + AI Summit (DAIS) の最新アジェンダから、ユーザーのユースケース（業界・技術・ユースケース）に合ったセッションを推薦する。
  トリガー: "DAIS", "Data AI Summit", "サミット", "セッション推薦", "おすすめセッション", "agenda"
  使用場面: (1) 特定業界・事業領域に役立つDAISセッションを探す、(2) 特定技術（Lakebase, Genie, Unity Catalog等）の事例収集、(3) 出張/視聴優先度の判断
  データソース: hosted slim JSON (raw URL、未設定時は agenda URL https://www.databricks.com/dataaisummit/agenda を直接取得)
---

# DAIS Session Recommender

Data + AI Summit の公式アジェンダから全セッション情報を取得し、**Claude自身が内容を読んで** ユーザーのユースケースに沿って推薦するスキル。

## 設計原則

- **軽量な slim JSON を主経路**にして、agenda直取得はフォールバック
- **推薦判断（スコアリング、優先度、なぜおすすめ）は Claude がやる**。スクリプトは取得と整形だけ、機械的マッチングは書かない
  - キーワード一致で並べ替えるとニュアンスを取りこぼす
  - 登壇企業の業界ポジション・事例規模・ユーザーの組織段階など、文脈依存の判断は Claude が行う
- **デフォルト値なし**。業界・件数等は必ずユーザーにヒアリング
- **画面表示のみ**。ファイル出力はユーザーが明示依頼した時だけ

## データソース

### 1) hosted slim JSON（推奨・環境非依存）

`scripts/fetch_sessions.py --format slim --with-metadata` の出力を公開URL（GitHub raw等）にホストして、そこから `WebFetch` で取得する。

- 配信URL: `https://raw.githubusercontent.com/akuwano/dotfiles/main/.claude/skills/dais-session-recommender/dais_sessions.slim.json`
- 更新: GitHub Actions で日次自動（`.github/workflows/refresh-dais-sessions.yml`、03:00 JST）
- Claude.ai アプリ含む全環境で WebFetch が使えれば動く

### 2) agenda HTML 直取得（フォールバック）

hosted JSONが無い / 古すぎる / 取れない時は、Databricksの公式agendaをそのまま WebFetch する。サマライズされる可能性があるため最終手段。

### スキーマ

`--with-metadata` 付きスクリプト出力 = 配信JSON:

```json
{
  "generated_at": "2026-04-23T05:21:24+00:00",
  "source_url": "https://www.databricks.com/dataaisummit/agenda",
  "session_count": 174,
  "sessions": [
    {
      "title": "...",
      "speakers": [{"name": "...", "role": "...", "company": "..."}],
      "type": "Breakout | Lightning Talk | Paid Training | Keynote",
      "track": "Data Engineering & Streaming 等",
      "industry": ["Financial Services", ...],
      "category": ["Lakebase", "Unity Catalog", ...],
      "level": "Beginner | Intermediate | Advanced",
      "areas": ["AI Agents", "Data Applications", ...],
      "duration_min": "40",
      "url": "https://www.databricks.com/session/...",
      "body": "概要600字まで"
    }
  ]
}
```

### 各セッションの原フィールド対応

| 配信JSONキー | agenda HTML の `sessions[]` 側キー |
|---|---|
| `speakers[].role` | `job_title` |
| `type` / `track` / `level` | `categories.type[0]` / `categories.track[0]` / `categories.level[0]` |
| `industry` / `category` | `categories.industry` / `categories.category` |
| `areas` | `categories.areasofinterest` |
| `duration_min` | `duration` |
| `url` | `https://www.databricks.com` + `alias` |
| `body` | `body`（HTMLタグ除去・600字切り詰め） |

## 実行手順

### Step 1: ヒアリング（必須）

ユーザーが条件を指定していない限り、以下を聞く:

- **業界/事業領域**（金融、保険、小売、製造、ヘルスケア、メディア、公共、指定なし）
- **関心ユースケース**（不正検知、Customer360、リアルタイム分析、コスト最適化、規制対応、基盤移行、AIエージェント など）
- **関心技術**（Lakebase, Genie, Unity Catalog, Agent Bricks, Delta Sharing, Lakeflow 等）
- **件数**（Top 10 / Top 20 / Top 30 / 全件）
- **視聴者の立場**（CxO・アーキテクト・データエンジニア・アナリスト等 — 推薦観点が変わる）

1つだけ指定でも実行OK。曖昧な場合は1往復だけ深掘り質問する。

### Step 2: セッション取得（3経路・上から順に試す）

#### 2-1（主経路・環境非依存）: hosted slim JSON を WebFetch

```
WebFetch(
  url="https://raw.githubusercontent.com/akuwano/dotfiles/main/.claude/skills/dais-session-recommender/dais_sessions.slim.json",
  prompt="このJSONの sessions 配列を丸ごと返してほしい。各要素は title / speakers / type / track / industry / category / level / areas / duration_min / url / body。要約せずそのまま。"
)
```

取得したら `generated_at` を確認し、**1週間以上古ければユーザーに「データが古い可能性あり、最新化しますか?」と一声かける**。

#### 2-2（高鮮度経路・Bash/Python使えるとき）: スクリプトで最新化

```bash
python3 scripts/fetch_sessions.py --format slim --with-metadata --output /tmp/dais_sessions.slim.json
```

- `--with-metadata`: `{generated_at, source_url, session_count, sessions}` でラップ（推奨）
- `--format full`: 全フィールド版が必要な時のみ
- `--body-chars N`: body切り詰め長さ（0=無制限）

Claude Code 等で使える。取得後は Read tool で読む。

#### 2-3（最終フォールバック）: agenda を WebFetch

2-1 の配信JSONも 2-2 のCLIも使えない場合のみ:

```
WebFetch(
  url="https://www.databricks.com/dataaisummit/agenda",
  prompt="このページのHTML中には `\"sessions\":[ ... ]` という JSON 配列がDrupal経由で埋め込まれている。その配列を**要約せず**、可能な限りそのまま返してほしい。各要素は title / speakers / body / alias / duration / categories(type, track, industry, category, level, areasofinterest) を持つ。"
)
```

WebFetchはサマライズされる可能性があるため**最終手段**。主経路ではない。

### Step 3: Claude が読む＋判断する

JSONを把握したら以下を内部で行う:

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
4. 末尾で「もっと絞る?」「別テーマで見る?」を提示

長すぎる時は必見と一覧だけ表示し、詳細は追加リクエストに応じる方針。

### Step 5: ファイル保存（依頼時のみ）

ユーザーが「ファイルに保存して」と言ったら、そのMarkdownを `.md` ファイルに書き出す。パスもユーザー確認。

## ファイル構成

```
dais-session-recommender/
├── SKILL.md
└── scripts/
    └── fetch_sessions.py        # 高鮮度経路 / 配信JSON生成用
```

配信JSONは **スキル外でホスト** する（repo同梱はしない）。

## スクリプト仕様

`scripts/fetch_sessions.py` — agenda HTMLからセッション配列を抽出

| フラグ | 役割 |
|---|---|
| `--format slim` | 要点のみ、body 600字切り詰め（デフォルト、推奨） |
| `--format full` | 全フィールド |
| `--format table` | 目視確認用 |
| `--with-metadata` | `{generated_at, source_url, session_count, sessions}` でラップ |
| `--body-chars N` | body切り詰め長さ（0=無制限） |
| `--output PATH` | 出力先（`-` でstdout） |

配信JSONを生成する場合:

```bash
python3 scripts/fetch_sessions.py --format slim --with-metadata --output dais_sessions.slim.json
```

できた `dais_sessions.slim.json` を公開repoにcommit→push、raw URLを SKILL.md のデータソース欄に登録する。

## 運用

- 配信URLが決まったら **SKILL.md のデータソース欄と Step 2-1 の `<配信URL>` を実URLに置換**
- 鮮度維持は手動更新でも OK。頻度が問題になれば GitHub Actions で日次自動化
- agendaのHTML構造が変わって `"sessions":[` が見つからなくなったら、スクリプトの `extract_sessions()` を調整

## よくある使い方

| ユーザー発話 | 動き |
|---|---|
| 「DAISで金融向けTop20」 | 業界=金融、件数=20で hosted JSON読む→推薦 |
| 「Lakebase事例集めて」 | hosted JSON読む→Lakebase関連を抜粋 |
| 「データエンジニア向け」 | 立場=DE、Data Engineering & Streamingトラック中心に読解 |
| 「最新化して」 | 2-2の `fetch_sessions.py` で最新化（ホスト更新も実施） |
| 「ファイル保存して」 | 直前の推薦結果を `.md` で保存 |

## 注意

- **Claudeが読む前提**なので、CLIで完結する複雑なフィルタ/ソートは実装しない
- **デフォルト値で勝手に走らない**。ユーザーに必ず条件を確認
- hosted JSON の `generated_at` は必ず確認し、古い時はユーザーに知らせる
