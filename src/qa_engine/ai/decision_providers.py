"""判断(decide)の実装。どれも DecisionProvider として同じように呼べる。

- SystemOneProvider:      TypeSafe 互換の /v1/systemone を呼ぶ(Jevクラウド / ローカルの Ollaya)
- LogprobDecisionProvider: OpenAI 互換の chat/completions の logprobs から確率を出す
                           (llama-server / Azure OpenAI の logprobs 対応モデル)
- CascadeDecisionProvider: 軽いプロバイダから順に聞き、確信度が足りない質問だけ次へ回す
"""

import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from qa_engine.ai.base import ProviderNotConfiguredError
from qa_engine.ai.decision import (
    Choice,
    DecisionError,
    DecisionProvider,
    DecisionResult,
    Noul,
    Question,
    Score,
    build_answer,
    questions_to_wire,
    result_from_wire,
)

PostJson = Callable[[str, dict, dict[str, str], float], dict]


def post_json(url: str, payload: dict, headers: dict[str, str], timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(detail)  # TypeSafe / Ollaya はエラーも JSON で返す
        except json.JSONDecodeError:
            raise DecisionError(f"HTTP {e.code}: {detail[:200]}") from e
    except urllib.error.URLError as e:
        raise DecisionError(f"接続できません({url}): {e.reason}") from e


def state_to_text(state: str | dict[str, Any]) -> str:
    if isinstance(state, str):
        return state
    return "\n".join(f"{key}: {value}" for key, value in state.items())


# --- TypeSafe 互換(Jev / Ollaya) ---------------------------------------------

class SystemOneProvider(DecisionProvider):
    """TypeSafe 互換の /v1/systemone を呼ぶ。Ollaya なら base_url は http://127.0.0.1:11435。"""

    def __init__(self, base_url: str | None, model: str | None, api_key: str | None = None,
                 timeout: float = 60.0, transport: PostJson = post_json):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.name = f"systemone:{model}"

    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        if not self.base_url or not self.model:
            raise ProviderNotConfiguredError("判断モデルの接続先(base_url / model)が未設定です。")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "state": state, "questions": questions_to_wire(questions)}
        data = self.transport(f"{self.base_url.rstrip('/')}/v1/systemone", payload, headers, self.timeout)
        result = result_from_wire(data)
        result.answered_by = {key: self.name for key in result.answers}
        return result


# --- OpenAI 互換 + logprobs ----------------------------------------------------

LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

SYSTEM_PROMPT = (
    "あなたは判定器です。与えられた「状態」を読み、「質問」に最も当てはまる選択肢を選びます。"
    "選択肢のラベル(英大文字1文字)だけを答えてください。説明は不要です。"
)


def _options(question: Question) -> list[tuple[str, str]]:
    """(回答のキー, 選択肢の説明) の一覧。キーは build_answer に渡す形にそろえる。"""
    if isinstance(question, Choice):
        return [(key, f"{key}({desc})" if desc and desc != key else key)
                for key, desc in question.criteria.items()]
    if isinstance(question, Score):
        return [(str(i), desc) for i, desc in enumerate(question.criteria)]
    criteria = question.criteria or {}
    return [("true", f"はい({criteria['true']})" if "true" in criteria else "はい"),
            ("false", f"いいえ({criteria['false']})" if "false" in criteria else "いいえ")]


def build_messages(state_text: str, question: Question) -> tuple[list[dict], dict[str, str]]:
    """状態を前、質問を後ろに置く(同じ状態に複数の質問を投げるとき、先頭のキャッシュが効く)。"""
    options = _options(question)
    if len(options) > len(LABELS):
        raise DecisionError(f"選択肢が多すぎます({len(options)}件。上限{len(LABELS)}件)")
    label_to_key = {LABELS[i]: key for i, (key, _) in enumerate(options)}
    lines = "\n".join(f"{LABELS[i]}: {desc}" for i, (_, desc) in enumerate(options))
    user = f"# 状態\n{state_text}\n\n# 質問\n{question.instructions}\n\n# 選択肢\n{lines}\n\n答え(ラベルのみ):"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}], label_to_key


def probabilities_from_logprobs(response: dict, label_to_key: dict[str, str]) -> dict[str, float]:
    """1トークン目の top_logprobs から、各ラベルの確率を集める(" A" と "A" などの表記違いは合算)。"""
    try:
        first = response["choices"][0]["logprobs"]["content"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise DecisionError("応答に logprobs が含まれていません(logprobs 非対応のモデル・サーバの可能性)") from e
    scores = {key: 0.0 for key in label_to_key.values()}
    for candidate in first.get("top_logprobs") or [first]:
        label = str(candidate.get("token", "")).strip().upper()
        if label in label_to_key:
            scores[label_to_key[label]] += math.exp(float(candidate["logprob"]))
    if sum(scores.values()) <= 0:
        raise DecisionError(f"上位の候補に選択肢のラベルがありません(先頭トークン: {first.get('token')!r})")
    return scores


class LogprobDecisionProvider(DecisionProvider):
    """OpenAI 互換 API(llama-server など)で、選択肢ラベル1トークンの確率から判断する。

    base_url は /v1 まで含める(例: http://127.0.0.1:8080/v1)。
    思考モードを持つモデルは extra_body で切っておく
    (llama-server の Qwen3 系なら {"chat_template_kwargs": {"enable_thinking": False}})。
    """

    def __init__(self, base_url: str | None, model: str | None, api_key: str | None = None,
                 extra_body: dict | None = None, top_logprobs: int = 20, concurrency: int = 1,
                 timeout: float = 120.0, transport: PostJson = post_json):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.extra_body = extra_body or {}
        self.top_logprobs = top_logprobs
        self.concurrency = concurrency
        self.timeout = timeout
        self.transport = transport
        self.name = f"logprobs:{model}"

    def _ask(self, state_text: str, question: Question) -> tuple[Any, int]:
        messages, label_to_key = build_messages(state_text, question)
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": self.top_logprobs,
            **self.extra_body,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = self.transport(f"{self.base_url.rstrip('/')}/chat/completions", payload, headers, self.timeout)
        if "error" in response:
            raise DecisionError(f"LLM サーバのエラー: {response['error']}")
        answer = build_answer(question, probabilities_from_logprobs(response, label_to_key))
        return answer, int((response.get("usage") or {}).get("prompt_tokens", 0))

    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        if not self.base_url or not self.model:
            raise ProviderNotConfiguredError("ローカルLLMの接続先(base_url / model)が未設定です。")
        state_text = state_to_text(state)
        keys = list(questions)
        if self.concurrency > 1:
            with ThreadPoolExecutor(self.concurrency) as pool:
                outputs = list(pool.map(lambda k: self._ask(state_text, questions[k]), keys))
        else:
            outputs = [self._ask(state_text, questions[k]) for k in keys]
        return DecisionResult(
            answers={k: answer for k, (answer, _) in zip(keys, outputs)},
            model=self.model or "",
            usage={"input_tokens": sum(tokens for _, tokens in outputs), "output_tokens": len(keys)},
            answered_by={k: self.name for k in keys},
        )


# --- 多段(軽い順に聞き、迷った質問だけ次へ) ----------------------------------------

class CascadeDecisionProvider(DecisionProvider):
    """stages は (プロバイダ, 確信度のしきい値) を軽い順に並べたもの。最後の段のしきい値は使わない。"""

    def __init__(self, stages: list[tuple[DecisionProvider, float]]):
        if not stages:
            raise ValueError("stages が空です")
        self.stages = stages
        self.name = " > ".join(p.name for p, _ in stages)

    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        result = DecisionResult(answers={})
        pending = dict(questions)
        for index, (provider, threshold) in enumerate(self.stages):
            stage = provider.decide(state, pending)
            last = index == len(self.stages) - 1
            for key, answer in stage.answers.items():
                if last or answer.confidence >= threshold:
                    result.answers[key] = answer
                    result.answered_by[key] = stage.answered_by.get(key, provider.name)
                    pending.pop(key, None)
            for name, count in stage.usage.items():
                result.usage[name] = result.usage.get(name, 0) + count
            if not pending:
                break
        result.answers = {key: result.answers[key] for key in questions if key in result.answers}
        return result


class TimedProvider(DecisionProvider):
    """計測用: 直近の decide にかかった秒数を残す。"""

    def __init__(self, inner: DecisionProvider):
        self.inner = inner
        self.name = inner.name
        self.last_seconds = 0.0

    def decide(self, state: str | dict[str, Any], questions: dict[str, Question]) -> DecisionResult:
        started = time.perf_counter()
        try:
            return self.inner.decide(state, questions)
        finally:
            self.last_seconds = time.perf_counter() - started
