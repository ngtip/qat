"""Jev(TypeSafe System One)型の判断インターフェース。

「状態(state) + 複数の質問(questions)」を渡すと、質問ごとに確率付きの判断が返る。
質問の型は TypeSafe と同じ3種類:

- Choice: 選択肢から1つ選ぶ。各選択肢の確率が返る
- Score:  段階評価(0〜段階数-1)。各段階の確率と、その期待値が返る
- Noul:   Yes/No。Yes の確率(0〜1)が返る

リクエスト/レスポンスの形は TypeSafe / Ollaya の /v1/systemone と同じにしてあり、
裏側(Jevクラウド・Ollaya・llama-server等のlogprobs)は providers 側で差し替える。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class DecisionError(Exception):
    pass


# --- 質問 ---------------------------------------------------------------------

@dataclass
class Choice:
    instructions: str
    criteria: dict[str, str]  # 選択肢のキー -> 説明

    def to_wire(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": self.criteria}


@dataclass
class Score:
    instructions: str
    criteria: list[str]  # 低い段階から順に並べた各段階の説明

    def to_wire(self) -> dict:
        return {"type": "score", "instructions": self.instructions, "criteria": self.criteria}


@dataclass
class Noul:
    instructions: str
    criteria: dict[str, str] | None = None  # {"true": "...", "false": "..."} の説明(任意)

    def to_wire(self) -> dict:
        wire = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            wire["criteria"] = self.criteria
        return wire


Question = Choice | Score | Noul


# --- 回答 ---------------------------------------------------------------------

@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass
class ScoreAnswer:
    score: float  # 各段階の確率で重み付けした期待値
    probabilities: dict[str, float]  # "0", "1", ... -> 確率
    confidence: float


@dataclass
class NoulAnswer:
    noul: float  # Yes の確率

    @property
    def confidence(self) -> float:
        return abs(self.noul - 0.5) * 2


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


@dataclass
class DecisionResult:
    answers: dict[str, Answer]
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    answered_by: dict[str, str] = field(default_factory=dict)  # 質問キー -> 回答したプロバイダ(多段時)


def margin(probabilities: dict[str, float]) -> float:
    """1位と2位の確率の差。迷っている度合いの目安として、プロバイダ間で共通に使う。"""
    top = sorted(probabilities.values(), reverse=True)
    return top[0] - (top[1] if len(top) > 1 else 0.0)


def normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        raise DecisionError("選択肢の確率が得られませんでした")
    return {k: v / total for k, v in scores.items()}


def build_answer(question: Question, probabilities: dict[str, float]) -> Answer:
    """選択肢キーごとの確率(Noulは "true"/"false")から回答を組み立てる。"""
    probabilities = normalize(probabilities)
    if isinstance(question, Choice):
        best = max(probabilities, key=probabilities.get)
        return ChoiceAnswer(best, probabilities, margin(probabilities))
    if isinstance(question, Score):
        expected = sum(int(k) * p for k, p in probabilities.items())
        return ScoreAnswer(expected, probabilities, margin(probabilities))
    return NoulAnswer(probabilities.get("true", 0.0))


# --- ワイヤ形式(TypeSafe / Ollaya 互換) ------------------------------------------

def questions_to_wire(questions: dict[str, Question]) -> dict[str, dict]:
    return {key: q.to_wire() for key, q in questions.items()}


def answer_from_wire(data: dict) -> Answer:
    kind = data.get("type")
    if kind == "choice":
        probabilities = {k: float(v) for k, v in (data.get("probabilities") or {}).items()}
        return ChoiceAnswer(str(data["choice"]), probabilities,
                            margin(probabilities) if probabilities else float(data.get("confidence", 0)))
    if kind == "score":
        probabilities = {str(k): float(v) for k, v in (data.get("probabilities") or {}).items()}
        return ScoreAnswer(float(data["score"]), probabilities,
                           margin(probabilities) if probabilities else float(data.get("confidence", 0)))
    if kind == "noul":
        return NoulAnswer(float(data["noul"]))
    raise DecisionError(f"不明な回答の型です: {kind!r}")


def result_from_wire(data: dict) -> DecisionResult:
    if "error" in data:
        raise DecisionError(f"{data.get('code', 'ERROR')}: {data['error']}")
    try:
        answers = {key: answer_from_wire(a) for key, a in data["answers"].items()}
    except (KeyError, TypeError, ValueError) as e:
        raise DecisionError(f"回答の形式を解釈できません: {e}") from e
    return DecisionResult(answers, str(data.get("model", "")), dict(data.get("usage") or {}))


# --- プロバイダ ----------------------------------------------------------------

class DecisionProvider(ABC):
    name = "decision"

    @abstractmethod
    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        """接続先が未設定なら ProviderNotConfiguredError、判断できなければ DecisionError を送出する。"""
