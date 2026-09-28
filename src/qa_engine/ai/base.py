"""AIプロバイダの共通インターフェース。

実装は manual_relay_provider(開発中/IDEチャット経由) / azure_provider(本番) /
local_llm_provider(将来、ローカルQwen等) を想定。呼び出し側はこのインターフェースにのみ依存する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HeaderInfo:
    columns: list[str]
    notes: str | None = None


@dataclass
class ColumnSuggestion:
    column_name: str
    reason: str
    recommended: bool


@dataclass
class WordMiningResult:
    term: str
    frequency: int
    ai_score: float


class AIProvider(ABC):
    @abstractmethod
    def extract_header(self, raw_text: str) -> HeaderInfo:
        """フリーフォーマットの入力からヘッダ情報を検出する。
        ヘッダが見つからない場合は例外を送出する想定。
        """

    @abstractmethod
    def suggest_columns(
        self, headers: list[str], sample_rows: list[dict]
    ) -> list[ColumnSuggestion]:
        """検出済みヘッダとサンプル行から、品質分析に使えそうな列を提案する。"""

    @abstractmethod
    def mine_words(self, texts: list[str]) -> list[WordMiningResult]:
        """定性分析用のワードマイニングを行う。"""
