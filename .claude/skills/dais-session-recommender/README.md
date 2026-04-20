# DAIS Session Recommender

Databricks Data + AI Summit (DAIS) の公式アジェンダから、ユーザーのユースケース（業界・技術・立場）に合ったセッションを推薦する Claude Code スキル。

## 何をするか

1. 公式アジェンダページ (`https://www.databricks.com/dataaisummit/agenda`) から全セッションを取得
2. Claude が各セッションの内容を読み込み、ユーザーの文脈に沿って優先度付けと推薦理由を生成
3. 必見セッション + 優先度一覧表を会話上に提示

機械的キーワードマッチではなく、登壇企業の業界ポジション・事例の規模感・視聴者の立場を考慮した文脈判断を Claude が行うのが特徴。

## トリガー

"DAIS", "Data AI Summit", "サミット", "セッション推薦", "おすすめセッション", "agenda"

## 構成

- `SKILL.md` — スキル定義（Claude Code が読み込むエントリポイント）
- `scripts/fetch_sessions.py` — agenda HTML からセッション配列を抽出する Python スクリプト
  - `--format slim`（デフォルト）: body を600字に切り詰めた軽量JSON
  - `--format full`: 全フィールドの生JSON
  - `--format table`: 目視確認用のパイプ区切りテーブル

## 使用例

| 発話 | 動作 |
|---|---|
| 「DAISで金融向けTop20」 | 業界=金融、件数=20で推薦 |
| 「Lakebase事例集めて」 | Lakebase関連セッションを抜粋 |
| 「データエンジニア向け」 | DE視点で Data Engineering トラック中心に推薦 |

詳細は [`SKILL.md`](SKILL.md) を参照。
