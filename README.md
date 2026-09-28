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

## AIプロバイダの切り替え

`src/qa_engine/ai/base.py` の `AIProvider` インターフェースを共通契約とし、以下を切り替えて使う。

- `manual_relay_provider.py` : 開発中、IDE付属チャットに人手で問い合わせる想定のプロバイダ
  (プロンプトを組み立てて提示し、貼り付けられた応答をパースする)。
  Streamlitはスクリプト再実行モデルのため、「プロンプト提示」と「応答受け取り」を
  `st.session_state` で2段階に分けて実装する必要がある(要検討)。
- `azure_provider.py` : 本番想定、Azure の API を呼び出す。
- `local_llm_provider.py` : 将来、ローカルのQwenなどを利用する。

どれを使うかは `src/qa_engine/config.py` で切り替える。

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
  analysis/               定量・定性分析、スコアリング
  storage/                SQLite接続・スキーマ
  report/                 出力フォーマット(分析結果から分離)
data/
  db/                     SQLiteファイル置き場(gitignore対象)
  samples/                動作確認用サンプル入力
scripts/
  smoke_test.py           UIを介さない全工程の疎通確認(一時DBを使用)
tests/
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
`data/samples/sample_defects.csv` を用意している。

ページ間の状態(現在のセッションID)は `st.session_state` で保持しているため、
ページ移動はサイドバーから行う(URL直打ちやリロードでは状態が消える)。

開発中にスキーマを変更した場合は `data/db/quality.sqlite3` を削除して再起動する
(マイグレーションの仕組みは未導入)。
