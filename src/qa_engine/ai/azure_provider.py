"""Azure OpenAI を呼び出すプロバイダ。接続は今後実装する。"""

from qa_engine.ai.base import AIProvider, ProviderNotConfiguredError


class AzureProvider(AIProvider):
    def __init__(self, endpoint: str | None, deployment: str | None):
        self.endpoint = endpoint
        self.deployment = deployment

    def complete(self, prompt: str) -> str:
        raise ProviderNotConfiguredError("Azure OpenAI の接続先は未設定です(今後対応予定)。")
