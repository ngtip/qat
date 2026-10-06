# 品質分析ツール

フリーフォーマットのデータを取り込み、AIによるヘッダ検出・列提案・行別チェック・
定量/定性分析を経て品質スコアを算出するローカルツール。UIはStreamlit。

## パイプライン概要

1. **取込 (ingestion)**: フリーフォーマットの入力を受け取り、AIでヘッダ情報を検出する。
   ヘッダが検出できないものは受け付けない。
2. **列提案 (column suggestion)**: 検出したヘッダを分析し、品質分析に使えそうな列をAIが提案。
   ユーザーがUI上でチェックして確定する。
3. **行別チェック (checks)**: 確定した列を対象に、重複検出などのチェック処理を行単位で実行する。
   チェックはプラグイン的に追加できる想定(`src/qa_engine/checks/`)。
   Levenshtein(`rapidfuzz`)は数あるチェック手法の一つとして、高速なスクリーニング用途で使う
   (意味的な重複は別途、埋め込みベースの類似度などと組み合わせる余地を残す)。
4. **定量・定性分析 (analysis)**:
   - 定量分析: チェック結果や統計値を集計。
   - 定性分析: AIによるワードマイニングを行い、結果をユーザーが確認して各要素に重みを付ける。
5. **スコアリング・出力 (scoring / report)**: 上記を統合して品質スコアを算出し、レポートとして出力する。
   分析結果(構造化データ)とレポート表示(フォーマット)は分離しており、
   出力形式の変更があっても再分析は不要。

## AIの呼び先の切り替え

AIに依頼する3工程(ヘッダ検出・列提案・ワードマイニング)のプロンプトと応答の解析は
`src/qa_engine/ai/tasks.py` にまとめてあり、どの呼び先でも同じものを使う。
呼び先は画面のサイドバー(既定値は環境変数 `QA_AI_PROVIDER`、`src/qa_engine/config.py`)で切り替える。

- 手動中継(`manual_relay`、既定): 画面に出るプロンプトをIDEのAIチャット(GitHub Copilot など)に貼り、
  返ってきた応答を画面に貼り戻す。Streamlitはスクリプト再実行モデルのため、
  「プロンプト提示」と「応答の取込」を分け、結果を `st.session_state` に保持する(`src/qa_engine/ui/ai_step.py`)。
- 簡易ロジック(`naive`): AIを使わない仮実装。オフラインでのリハーサル用。
- Azure OpenAI(`azure`)/ ローカルLLM(`local_llm`): `AIProvider.complete(prompt)` を持つ自動呼び出し型。
  今は接続先未設定のスタブ(`azure_provider.py` / `local_llm_provider.py`)。

AIとのやり取り(送ったプロンプトと応答)はすべて `ai_interactions` テーブルに記録し、
分析結果画面の「AI処理ログ」とExcelレポートで確認できる。

### 判断モデル(Jev型)

選択・判定のような「答えが決まった候補から選ぶ」処理は、文章を生成させずに
Jev(TypeSafe System One)型の `decide(state, questions)` で確率付きの判断として受け取る
(`src/qa_engine/ai/decision.py`)。質問の型は Choice(選択)/ Score(段階評価)/ Noul(Yes/No)。

- `SystemOneProvider`: TypeSafe 互換 API(Jev クラウド、ローカルの Ollaya `http://127.0.0.1:11435`)
- `LogprobDecisionProvider`: OpenAI 互換 API の logprobs から確率を出す(llama-server、Azure OpenAI)
- `CascadeDecisionProvider`: ルール(`decision_tasks.RuleDecisionProvider`)など軽い段から聞き、
  確信度が足りない質問だけ重い段へ回す

精度と速度は `scripts/benchmark_decisions.py` で、ダミーデータの正解付きケースを使って比べる
(使い方はスクリプト冒頭のコメント。結果は `data/bench/` に保存)。

## DB設計

短期分析(取込データのみでの判定)から始めるが、`src/qa_engine/storage/schema.sql` の通り
最初からSQLiteでセッション単位に結果を永続化する。中長期分析(蓄積データを跨いだ分析)は
将来、同じテーブル群に対するクエリを追加するだけで拡張できるようにしておく。

## ディレクトリ構成

```
app.py                  Streamlitエントリポイント
pages/                  Streamlitのマルチページ(取込〜結果表示までの各画面)
src/qa_engine/
  config.py              設定(AIプロバイダの切り替え等)
  ai/                     AIプロバイダの抽象化と実装
  ingestion/              ヘッダ検出・列提案
  checks/                 行別チェック処理(プラグイン的に追加)
  analysis/               定量・定性分析、スコアリング(暫定ロジック)
  storage/                SQLite接続・スキーマ
  report/                 レポートの組み立てとExcel出力(分析結果から分離)
  ui/                     画面共通部品(サイドバー、AI工程の実行)
data/
  db/                     SQLiteファイル置き場(gitignore対象)
  samples/                動作確認用サンプル入力(架空データ)
scripts/
  smoke_test.py           UIを介さない全工程の疎通確認(一時DBを使用)
  generate_demo_data.py   デモ用ダミー障害票の生成(固定シード)
tests/
  fixtures/               応答パーサの検証用の固定応答(検証専用)
docs/
  DEMO_RUNBOOK.md         会社PCでのデモ手順(人が読む用)
SETUP_FOR_AI.md           別PCでAIエージェントに環境構築させるための手順書
```

## セットアップ

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install -e .    # src/qa_engine を import 可能にする
.venv/Scripts/python -m streamlit run app.py
```

プロジェクトルートで起動すること(DBパスが相対パスのため)。動作確認用に
ソフト開発の障害票を模した架空データ `data/samples/bug_tickets_demo.csv`(80件)を用意している。

ページ間の状態(現在のセッションID)は `st.session_state` で保持しているため、
ページ移動はサイドバーから行う(URL直打ちやリロードでは状態が消える)。

開発中にスキーマを変更した場合は `data/db/quality.sqlite3` を削除して再起動する
(マイグレーションの仕組みは未導入)。
