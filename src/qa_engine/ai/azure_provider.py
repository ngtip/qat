"""本番想定、Azure の API を呼び出すプロバイダ。"""

from qa_engine.ai.base import AIProvider, ColumnSuggestion, HeaderInfo, WordMiningResult


class AzureProvider(AIProvider):
    def __init__(self, endpoint: str, api_key: str, deployment: str):
        self.endpoint = endpoint
        self.api_key = api_key
        self.deployment = deployment

    def extract_header(self, raw_text: str) -> HeaderInfo:
        raise NotImplementedError

    def suggest_columns(
        self, headers: list[str], sample_rows: list[dict]
    ) -> list[ColumnSuggestion]:
        raise NotImplementedError

    def mine_words(self, texts: list[str]) -> list[WordMiningResult]:
        raise NotImplementedError
