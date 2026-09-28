"""開発中に使う、IDE付属チャットへの手動中継プロバイダ。

Streamlitはスクリプト再実行モデルのため、ここでの「プロンプト作成」と「応答パース」は
呼び出し側(pages側)で st.session_state を使って2段階に分けて呼び出す想定:
  1. build_prompt() の結果を画面に表示し、ユーザーがIDEチャットに貼り付けて実行
  2. 得られた応答を貼り付けてもらい parse_response() でパースする
"""

from qa_engine.ai.base import AIProvider, ColumnSuggestion, HeaderInfo, WordMiningResult


class ManualRelayProvider(AIProvider):
    def build_prompt_for_header(self, raw_text: str) -> str:
        raise NotImplementedError

    def parse_header_response(self, response_text: str) -> HeaderInfo:
        raise NotImplementedError

    # AIProvider インターフェースの実装(自動呼び出し用)。
    # 手動中継の性質上、pages側では build_prompt_for_*/parse_*_response を直接使う想定で、
    # 以下は将来の整合性のために残す。
    def extract_header(self, raw_text: str) -> HeaderInfo:
        raise NotImplementedError("手動中継はpages側で2段階に分けて呼び出してください")

    def suggest_columns(
        self, headers: list[str], sample_rows: list[dict]
    ) -> list[ColumnSuggestion]:
        raise NotImplementedError("手動中継はpages側で2段階に分けて呼び出してください")

    def mine_words(self, texts: list[str]) -> list[WordMiningResult]:
        raise NotImplementedError("手動中継はpages側で2段階に分けて呼び出してください")
