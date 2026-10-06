"""AIに依頼する3つのタスク(ヘッダ検出・列提案・ワードマイニング)のプロンプト生成と応答パース。

どのプロバイダ(手動中継 / Azure / ローカルLLM)でも同じプロンプトと同じパーサを使う。
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qa_engine.ai.base import ROLES, ColumnSuggestion, HeaderInfo, WordMiningResult
from qa_engine.ingestion.header_detector import HeaderNotFoundError

HEAD_LINE_LIMIT = 30
WORD_LIMIT = 30
WORD_CATEGORIES = ["機能", "現象", "原因", "対策", "その他"]


class AIResponseError(Exception):
    pass


@dataclass(frozen=True)
class AITask:
    key: str
    label: str
    build_prompt: Callable[..., str]
    parse_response: Callable[..., Any]


def extract_json(text: str) -> Any:
    """応答テキストからJSONを取り出す。```json``` の囲みや前後の説明文があっても読めるようにする。"""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = (fenced.group(1) if fenced else text).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (candidate.find("{"), candidate.find("[")) if i != -1]
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    if starts and end > min(starts):
        try:
            return json.loads(candidate[min(starts): end + 1])
        except json.JSONDecodeError:
            pass
    raise AIResponseError("応答からJSONを読み取れませんでした。AIの応答をそのまま貼り付けてください。")


# --- ヘッダ検出 ---------------------------------------------------------------

def build_header_prompt(head_lines: list[str]) -> str:
    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(head_lines[:HEAD_LINE_LIMIT]))
    return (
        "あなたはデータ取込の補助をします。以下は、ある表形式データの先頭部分です"
        "(各行の先頭に、0から始まる行番号と「: 」を付けています)。\n"
        "表のヘッダ(列名)が書かれている行を特定し、JSONだけを返してください。\n\n"
        "返す形式:\n"
        '{"header_row_index": 2, "delimiter": ",", "columns": ["列名1", "列名2"]}\n'
        "- header_row_index はヘッダ行の行番号です。\n"
        '- delimiter はカンマなら ","、タブなら "\\t" と書いてください。\n'
        '- ヘッダが見当たらない場合は {"error": "no_header"} を返してください。\n\n'
        "--- データ先頭 ---\n"
        f"{numbered}"
    )


def _normalize_delimiter(value: Any) -> str:
    text = str(value)
    if text in ("\\t", "\t", "tab", "TAB", "タブ"):
        return "\t"
    if text in (",", "カンマ", "comma"):
        return ","
    if len(text) == 1:
        return text
    raise AIResponseError(f"区切り文字を解釈できません: {text!r}")


def parse_header_response(text: str, **_: Any) -> HeaderInfo:
    data = extract_json(text)
    if not isinstance(data, dict):
        raise AIResponseError("ヘッダ検出の応答はJSONオブジェクトである必要があります。")
    if data.get("error"):
        raise HeaderNotFoundError("AIがヘッダを検出できませんでした(ヘッダの無いデータは受け付けません)")
    try:
        index = int(data["header_row_index"])
        columns = [str(c).strip() for c in data["columns"]]
        delimiter = _normalize_delimiter(data["delimiter"])
    except (KeyError, TypeError, ValueError) as e:
        raise AIResponseError(f"ヘッダ検出の応答に必要な項目がありません: {e}") from e
    return HeaderInfo(header_row_index=index, delimiter=delimiter, columns=columns, notes="AI検出")


HEADER_DETECTION = AITask("header_detection", "ヘッダ検出", build_header_prompt, parse_header_response)


# --- 列提案 -------------------------------------------------------------------

def build_column_prompt(columns: list[str], sample_rows: list[dict]) -> str:
    role_list = "、".join(f"{key}({label})" for key, label in ROLES.items())
    samples = "\n".join(json.dumps(row, ensure_ascii=False) for row in sample_rows)
    return (
        "以下は、品質分析(不具合・障害・問い合わせの記録など)に使うデータの列名とサンプル行です。\n"
        "各列について、役割(role)、品質分析に使うべきか(recommended)、その理由(reason)を判定し、"
        "JSONだけを返してください。\n\n"
        f"role は次のいずれか: {role_list}\n\n"
        "返す形式:\n"
        '[{"column": "列名", "role": "category", "recommended": true, "reason": "理由(30字以内)"}, ...]\n\n'
        f"列名: {json.dumps(columns, ensure_ascii=False)}\n"
        "サンプル行:\n"
        f"{samples}"
    )


def parse_column_response(text: str, columns: list[str], **_: Any) -> list[ColumnSuggestion]:
    data = extract_json(text)
    if not isinstance(data, list):
        raise AIResponseError("列提案の応答はJSON配列である必要があります。")
    by_column: dict[str, ColumnSuggestion] = {}
    for item in data:
        if not isinstance(item, dict) or str(item.get("column", "")).strip() not in columns:
            continue
        column = str(item["column"]).strip()
        role = str(item.get("role", "other"))
        by_column[column] = ColumnSuggestion(
            column_name=column,
            role=role if role in ROLES else "other",
            recommended=bool(item.get("recommended", False)),
            reason=str(item.get("reason", "")),
        )
    if not by_column:
        raise AIResponseError("列提案の応答に、データの列名と一致する項目がありませんでした。")
    return [
        by_column.get(c, ColumnSuggestion(c, "other", False, "AIの応答に含まれていなかった列"))
        for c in columns
    ]


COLUMN_SUGGESTION = AITask("column_suggestion", "列提案", build_column_prompt, parse_column_response)


# --- ワードマイニング -----------------------------------------------------------

def build_word_prompt(texts: list[str]) -> str:
    body = "\n".join(t for t in texts if t.strip())
    return (
        "以下は、品質に関する記録の自由記述欄の本文です(1行1件)。\n"
        f"品質上の傾向をつかむために重要な語句(機能、現象、原因、対策などを表す語)を最大{WORD_LIMIT}件抽出し、"
        "JSONだけを返してください。\n"
        "- term は本文中にそのまま出てくる表記にしてください(出現回数はこちらで数えます)。\n"
        "- importance は品質分析上の重要度を 0〜1 の数値で付けてください。\n"
        f"- category は {'・'.join(WORD_CATEGORIES)} のいずれかにしてください。\n\n"
        "返す形式:\n"
        '[{"term": "語句", "importance": 0.8, "category": "現象"}, ...]\n\n'
        "--- 本文 ---\n"
        f"{body}"
    )


def parse_word_response(text: str, texts: list[str], **_: Any) -> list[WordMiningResult]:
    data = extract_json(text)
    if not isinstance(data, list):
        raise AIResponseError("ワードマイニングの応答はJSON配列である必要があります。")
    results: dict[str, WordMiningResult] = {}
    for item in data:
        if not isinstance(item, dict) or not str(item.get("term", "")).strip():
            continue
        term = str(item["term"]).strip()
        frequency = sum(t.count(term) for t in texts)
        if frequency == 0 or term in results:
            continue
        try:
            importance = min(max(float(item.get("importance", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            importance = 0.5
        category = str(item.get("category", "その他"))
        results[term] = WordMiningResult(
            term=term,
            frequency=frequency,
            ai_score=round(importance, 3),
            category=category if category in WORD_CATEGORIES else "その他",
        )
    if not results:
        raise AIResponseError("ワードマイニングの応答に、本文中に出てくる語句がありませんでした。")
    return sorted(results.values(), key=lambda r: (-r.ai_score, -r.frequency))[:WORD_LIMIT]


WORD_MINING = AITask("word_mining", "ワードマイニング", build_word_prompt, parse_word_response)
