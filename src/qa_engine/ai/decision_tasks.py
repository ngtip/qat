"""品質分析の各判断を Jev 型の質問(state + questions)に落とし込む。

ルールで答えられるものは RuleDecisionProvider で先に答え、迷ったものだけ LLM 側へ回す
(CascadeDecisionProvider の1段目に置く想定)。
"""

import csv
import io
from collections.abc import Callable
from typing import Any

from rapidfuzz import fuzz

from qa_engine.ai.base import ROLES
from qa_engine.ai.decision import (
    Choice,
    DecisionError,
    DecisionProvider,
    DecisionResult,
    Noul,
    Question,
    build_answer,
)
from qa_engine.ingestion.column_suggester import _RECOMMENDED_ROLES, _guess_role

HEAD_LINE_LIMIT = 30
LINE_PREVIEW = 80
MAX_HEADER_CANDIDATES = 10  # ヘッダはデータ行より前にあるので、先頭の候補だけで足りる


# --- ヘッダ検出: 「どの行がヘッダか」を1つの Choice にする -------------------------------

def header_candidates(head_lines: list[str]) -> tuple[str, list[int]]:
    """区切り文字と、ヘッダになりうる行(2列以上に区切れる行)の番号(先頭から最大10件)。"""
    lines = head_lines[:HEAD_LINE_LIMIT]
    delimiter = "\t" if any("\t" in line for line in lines) else ","
    candidates = []
    for i, line in enumerate(lines):
        fields = next(csv.reader(io.StringIO(line), delimiter=delimiter), [])
        if len([f for f in fields if f.strip()]) >= 2:
            candidates.append(i)
    return delimiter, candidates[:MAX_HEADER_CANDIDATES]


def header_question(head_lines: list[str]) -> tuple[str, dict[str, Question]]:
    _, candidates = header_candidates(head_lines)
    if not candidates:
        raise DecisionError("2列以上に区切れる行がありません(ヘッダの無いデータは受け付けません)")
    # 候補行の内容は選択肢の説明に入れるので、状態には候補にならなかった行(表題や注記)だけを書く。
    others = [f"{i}: {line[:LINE_PREVIEW]}" for i, line in enumerate(head_lines[:HEAD_LINE_LIMIT])
              if i not in candidates and line.strip()]
    state = "表形式データの先頭部分。選択肢は、2列以上に区切れる行の内容。"
    if others:
        state += "\n区切れなかった行(表題・注記など):\n" + "\n".join(others)
    criteria = {str(i): head_lines[i][:LINE_PREVIEW] for i in candidates}
    return state, {"header": Choice("表のヘッダ(列名)が書かれている行はどれか", criteria)}


# --- 列提案: 列ごとに「役割」と「分析に使うか」を聞く --------------------------------

ROLE_QUESTION = Choice("この列の役割はどれか", dict(ROLES))
USE_QUESTION = Noul(
    "この列は品質分析(不具合の傾向・原因・重要度の把握)に使うべきか",
    {"true": "分析に使う", "false": "識別子や担当者名など、分析には使わない"},
)


def column_state(column: str, values: list[str], sample_size: int = 8) -> dict[str, str]:
    samples = [v for v in values if v][:sample_size]
    return {"列名": column, "値の例": " / ".join(samples) if samples else "(空)"}


def column_questions() -> dict[str, Question]:
    return {"role": ROLE_QUESTION, "use": USE_QUESTION}


# --- 重複判定: 2件の記述が同じ事象か ------------------------------------------------

DUPLICATE_QUESTION = Noul(
    "記述Aと記述Bは、表記は違っても同じ不具合(同じ現象)を報告しているか",
    {"true": "同じ不具合", "false": "別の不具合"},
)


def duplicate_state(text_a: str, text_b: str) -> dict[str, str]:
    return {"記述A": text_a, "記述B": text_b}


# --- ルールで答える1段目 ---------------------------------------------------------

Rule = Callable[[str | dict[str, Any], Question], dict[str, float]]


def _spread(keys: list[str], best: str | None, weight: float) -> dict[str, float]:
    """best に weight、残りを均等に配る。best が無ければ一様。"""
    if best is None or len(keys) == 1:
        return {k: 1.0 for k in keys}
    rest = (1.0 - weight) / (len(keys) - 1)
    return {k: (weight if k == best else rest) for k in keys}


def header_rule(state: str | dict[str, Any], question: Question) -> dict[str, float]:
    """最も多くの列に区切れる最初の行を推す。最大列数の行が1つだけなら自信を持つ。"""
    assert isinstance(question, Choice)
    counts = {k: len(next(csv.reader(io.StringIO(v), delimiter="\t" if "\t" in v else ","), []))
              for k, v in question.criteria.items()}
    best_count = max(counts.values())
    tops = [k for k, c in counts.items() if c == best_count]
    return _spread(list(counts), tops[0], 0.9 if len(tops) == 1 else 0.5)


# 列の値の形から判断できる役割(パターン一致)は自信を持ち、列名や文字数からの推測は控えめにする。
_CONFIDENT_ROLES = {"id", "date", "numeric"}


def _column_values(state: dict[str, Any]) -> list[str]:
    raw = str(state.get("値の例", ""))
    return [] if raw == "(空)" else [v.strip() for v in raw.split(" / ")]


def column_role_rule(state: str | dict[str, Any], question: Question) -> dict[str, float]:
    assert isinstance(state, dict) and isinstance(question, Choice)
    role, _ = _guess_role(str(state["列名"]), _column_values(state))
    return _spread(list(question.criteria), role, 0.9 if role in _CONFIDENT_ROLES else 0.55)


def column_use_rule(state: str | dict[str, Any], question: Question) -> dict[str, float]:
    assert isinstance(state, dict)
    role, _ = _guess_role(str(state["列名"]), _column_values(state))
    use = role in _RECOMMENDED_ROLES
    strength = 0.9 if role in _CONFIDENT_ROLES | {"id", "person"} else 0.65
    return {"true": strength if use else 1 - strength, "false": 1 - strength if use else strength}


def duplicate_rule(state: str | dict[str, Any], question: Question) -> dict[str, float]:
    """文字列の近さ(rapidfuzz)をそのまま確率の目安にする。中間の値は迷いとして次段へ回る。"""
    assert isinstance(state, dict)
    similarity = fuzz.ratio(str(state["記述A"]), str(state["記述B"])) / 100
    return {"true": similarity, "false": 1 - similarity}


class RuleDecisionProvider(DecisionProvider):
    """質問キーごとのルール関数で答える。ルールの無い質問は「分からない」(一様分布)にする。"""

    name = "rules"

    def __init__(self, rules: dict[str, Rule]):
        self.rules = rules

    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        answers = {}
        for key, question in questions.items():
            rule = self.rules.get(key)
            if rule:
                probabilities = rule(state, question)
            elif isinstance(question, Noul):
                probabilities = {"true": 0.5, "false": 0.5}
            else:
                keys = list(question.criteria) if isinstance(question, Choice) else \
                    [str(i) for i in range(len(question.criteria))]
                probabilities = {k: 1.0 for k in keys}
            answers[key] = build_answer(question, probabilities)
        return DecisionResult(answers, "rules", {}, {k: self.name for k in answers})


DEFAULT_RULES: dict[str, Rule] = {
    "header": header_rule,
    "role": column_role_rule,
    "use": column_use_rule,
    "duplicate": duplicate_rule,
}
