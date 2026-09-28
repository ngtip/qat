"""AIプロバイダなど、環境によって切り替える設定をまとめる場所。"""

from dataclasses import dataclass


@dataclass
class Settings:
    ai_provider: str = "manual_relay"  # "manual_relay" / "azure" / "local_llm"
    db_path: str = "data/db/quality.sqlite3"


def load_settings() -> Settings:
    # TODO: 環境変数や設定ファイルからの読み込みに置き換える
    return Settings()
