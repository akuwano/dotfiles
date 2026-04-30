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

GitHub Actions で日次自動更新（03:00 JST、`.github/workflows/refresh-dais-sessions.yml`）。3形式を同時にホスト：

| 用途 | URL | サイズ | 説明 |
|---|---|---|---|
| **主経路（curl + Read）** | `https://raw.githubusercontent.com/akuwano/dotfiles/main/.claude/skills/dais-session-recommender/dais_sessions.jsonl` | ~310KB / 270行 | 1セッション=1行のJSONL。先頭行はメタデータ。Read で全件確実に読める |
| 詳細閲覧用 | `…/dais_sessions.slim.json` | ~390KB | indented JSON、body 600字含む |
| WebFetch フォールバック | `…/dais_sessions.index.json` | ~150KB | body無し compact JSON。Bash 不可環境用 |

### なぜ JSONL を主にするか

- **WebFetch は要約する**: LLMベース抽出のため、大きな配列を勝手にサマライズしてしまう。コーナーケースのセッションを見落とす
- **curl + Read なら要約ゼロ**: ファイルそのままを行単位で取得できる
- **JSONL は1行=1要素**: Read のページングと相性が良い、行数 = セッション数 + 1（メタ行）で件数確認も簡単

### スキーマ（jsonl）

```
# 1行目: メタデータ
{"generated_at":"2026-04-30T...","source_url":"https://...","session_count":269,"_format":"jsonl",...}
# 2行目以降: 1セッション = 1行（slim形式）
{"title":"...","speakers":[{"name":"...","role":"...","company":"..."}],"type":"Breakout","track":"...","industry":[...],"category":[...],"level":"Intermediate","areas":[...],"duration_min":"40","url":"https://www.databricks.com/session/...","body":"概要600字まで"}
{"title":"...",...}
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

**実行環境を判定しつつ、上から順に試して最初に成功した経路を使う**。経路1がベスト、ダメなら2、最後に3。

WebFetch は LLM ベース抽出のため大きな配列を要約してしまう（実測：156KB 程度でも全件保証されない）。可能な限り経路1か2で **生のファイルを取得して Read で読む** 流れを優先する。

---

#### 経路1（主経路 / Claude Code 環境）: スクリプト直接実行

```bash
python3 ~/.claude/skills/dais-session-recommender/scripts/fetch_sessions.py \
  --format jsonl \
  --with-metadata \
  --output ~/.claude/skills/dais-session-recommender/.cache/dais_sessions.jsonl
```

その後：
```
Read ~/.claude/skills/dais-session-recommender/.cache/dais_sessions.jsonl
```

- 常に最新（agenda から都度取得、~5秒）
- Python スクリプトが auto-mkdir するので事前準備不要
- `~` は macOS / Linux / Git Bash / WSL いずれでも展開される
- スクリプトは標準ライブラリのみ（urllib, json, re）、追加 install 不要

**Python が無い・スクリプトパスが解決できない場合は経路2へ**。

---

#### 経路2（フォールバック / Bash あるが Python なし）: hosted JSONL を curl で DL

```bash
mkdir -p ~/.claude/skills/dais-session-recommender/.cache
curl -sL https://raw.githubusercontent.com/akuwano/dotfiles/main/.claude/skills/dais-session-recommender/dais_sessions.jsonl \
  -o ~/.claude/skills/dais-session-recommender/.cache/dais_sessions.jsonl
```

その後：
```
Read ~/.claude/skills/dais-session-recommender/.cache/dais_sessions.jsonl
```

- GitHub Actions が日次更新している hosted ファイルを直接取得
- ~310KB / 270行（先頭行はメタデータ、残り269行が1セッション=1行）
- CDN 経由で速い（5分キャッシュ）

**curl も無い・Bash 自体無い場合は経路3へ**。

---

#### 経路3（最終手段 / WebFetch のみ）: hosted index を WebFetch

Claude.ai web app など Bash が使えない環境用：

```
WebFetch(
  url="https://raw.githubusercontent.com/akuwano/dotfiles/main/.claude/skills/dais-session-recommender/dais_sessions.index.json",
  prompt="このJSONの sessions 配列を全要素そのまま返してほしい。要約・抜粋せず全件。各要素は title / speakers / type / track / industry / category / level / areas / duration_min / url を持つ（bodyは無い）。"
)
```

取得後、`session_count` と実際に返ってきた配列の件数を必ず比較。乖離がある場合は **WebFetch がサマライズしている** ので、ユーザーに「現環境では全件取得が保証されない、Bash 環境での再実行を勧める」と伝える。

body が必要な候補は個別 session の `url` を WebFetch で開く（公式ページから1件ずつ取る方が確実）。

---

### Step 2-α: 取得直後の健全性チェック（経路問わず必須）

取得方法に関わらず、以下を確認：

1. **`generated_at` を読む**。1週間以上古ければユーザーに「データが古い可能性あり、最新化しますか?」と一声かける（経路1の再実行で最新化される）
2. **件数照合**: `session_count` メタデータと実際にロードされた件数を比較
   - JSONL: `wc -l` の値が `session_count + 1` （メタ行+1）と一致するか
   - JSON 配列: `len(sessions)` と `session_count` が一致するか
   - 不一致 → 経路2/3で取得が不完全。経路1へ昇格を試みる

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
