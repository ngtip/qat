"""AIの呼び先の一覧と、自動呼び出し型プロバイダの生成。

manual_relay(IDEのAIチャットへの手動中継)と naive(AIを使わない簡易ロジック)は
画面側(qa_engine.ui.ai_step)で処理するため、ここではプロバイダを生成しない。
"""

from qa_engine.ai.azure_provider import AzureProvider
from qa_engine.ai.base import AIProvider
from qa_engine.ai.local_llm_provider import LocalLLMProvider
from qa_engine.config import Settings

PROVIDER_LABELS = {
    "manual_relay": "手動中継(IDEのAIチャット)",
    "naive": "簡易ロジック(AIを使わない)",
    "azure": "Azure OpenAI(未設定)",
    "local_llm": "ローカルLLM(未設定)",
}


def get_provider(name: str, settings: Settings) -> AIProvider | None:
    if name == "azure":
        return AzureProvider(settings.azure_endpoint, settings.azure_deployment)
    if name == "local_llm":
        return LocalLLMProvider(settings.local_llm_base_url, settings.local_llm_model)
    return None
