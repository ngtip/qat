"""環境によって切り替える設定。環境変数で上書きできる。"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    ai_provider: str = "manual_relay"  # manual_relay / naive / azure / local_llm
    db_path: str = "data/db/quality.sqlite3"
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    local_llm_base_url: str | None = None
    local_llm_model: str | None = None


def load_settings() -> Settings:
    return Settings(
        ai_provider=os.environ.get("QA_AI_PROVIDER", "manual_relay"),
        db_path=os.environ.get("QA_DB_PATH", "data/db/quality.sqlite3"),
        azure_endpoint=os.environ.get("QA_AZURE_ENDPOINT"),
        azure_deployment=os.environ.get("QA_AZURE_DEPLOYMENT"),
        local_llm_base_url=os.environ.get("QA_LOCAL_LLM_BASE_URL"),
        local_llm_model=os.environ.get("QA_LOCAL_LLM_MODEL"),
    )
