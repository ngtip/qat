"""ローカルLLM(OpenAI互換APIを持つ llama-server など)を呼び出すプロバイダ。接続は今後実装する。"""

from qa_engine.ai.base import AIProvider, ProviderNotConfiguredError


class LocalLLMProvider(AIProvider):
    def __init__(self, base_url: str | None, model: str | None):
        self.base_url = base_url
        self.model = model

    def complete(self, prompt: str) -> str:
        raise ProviderNotConfiguredError("ローカルLLMの接続先は未設定です(今後対応予定)。")
