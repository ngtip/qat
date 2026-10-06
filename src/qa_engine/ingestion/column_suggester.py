"""AIを使わない簡易の列提案。AI経由の提案と同じ ColumnSuggestion を返す。"""

import re

from qa_engine.ai.base import ColumnSuggestion

_DATE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_RECOMMENDED_ROLES = {"date", "category", "severity", "free_text", "numeric"}


def _guess_role(name: str, values: list[str]) -> tuple[str, str]:
    if not values:
        return "other", "値が空"
    ratio = lambda pattern: sum(bool(pattern.match(v)) for v in values) / len(values)  # noqa: E731
    unique = len(set(values))
    if any(k in name for k in ("ID", "Id", "番号", "No")) and unique / len(values) > 0.9:
        return "id", "列名と値の一意性から識別子と判定"
    if ratio(_DATE) >= 0.8:
        return "date", "日付形式の値が大半"
    if any(k in name for k in ("重要度", "優先度", "ランク", "深刻度")):
        return "severity", "列名から重要度と判定"
    if ratio(_NUMBER) >= 0.8:
        return "numeric", "数値の値が大半"
    if any(k in name for k in ("担当", "起票者", "作成者", "氏名")):
        return "person", "列名から人と判定"
    if sum(len(v) for v in values) / len(values) >= 12:
        return "free_text", "長い文章が多い"
    if unique <= max(10, len(values) * 0.3):
        return "category", "値の種類が少ない"
    return "other", "判定できず"


def suggest_columns_naive(columns: list[str], rows: list[dict]) -> list[ColumnSuggestion]:
    suggestions = []
    for column in columns:
        values = [str(r.get(column, "")).strip() for r in rows if str(r.get(column, "")).strip()]
        role, reason = _guess_role(column, values)
        suggestions.append(ColumnSuggestion(column, role, role in _RECOMMENDED_ROLES, f"簡易判定: {reason}"))
    return suggestions
