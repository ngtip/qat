"""AI処理で受け渡すデータ型と、自動呼び出し型プロバイダの共通インターフェース。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

ROLES = {
    "id": "識別子",
    "date": "日付",
    "category": "分類",
    "severity": "重要度",
    "free_text": "自由記述",
    "numeric": "数値",
    "person": "人",
    "other": "その他",
}


@dataclass
class HeaderInfo:
    header_row_index: int
    delimiter: str
    columns: list[str]
    notes: str | None = None


@dataclass
class ColumnSuggestion:
    column_name: str
    role: str
    recommended: bool
    reason: str


@dataclass
class WordMiningResult:
    term: str
    frequency: int
    ai_score: float
    category: str | None = None


class ProviderNotConfiguredError(Exception):
    pass


class AIProvider(ABC):
    """プロンプトを送り、応答テキストを受け取る自動呼び出し型のプロバイダ(Azure / ローカルLLM)。"""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """接続先が未設定なら ProviderNotConfiguredError を送出する。"""
