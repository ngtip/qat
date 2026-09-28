"""将来、ローカルのQwen等を利用するプロバイダ。"""

from qa_engine.ai.base import AIProvider, ColumnSuggestion, HeaderInfo, WordMiningResult


class LocalLLMProvider(AIProvider):
    def __init__(self, model_path: str):
        self.model_path = model_path

    def extract_header(self, raw_text: str) -> HeaderInfo:
        raise NotImplementedError

    def suggest_columns(
        self, headers: list[str], sample_rows: list[dict]
    ) -> list[ColumnSuggestion]:
        raise NotImplementedError

    def mine_words(self, texts: list[str]) -> list[WordMiningResult]:
        raise NotImplementedError
