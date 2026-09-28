"""検出済みヘッダから、品質分析に使えそうな列をAIに提案させる。"""

from qa_engine.ai.base import AIProvider, ColumnSuggestion


def suggest_columns(
    provider: AIProvider, headers: list[str], sample_rows: list[dict]
) -> list[ColumnSuggestion]:
    return provider.suggest_columns(headers, sample_rows)
