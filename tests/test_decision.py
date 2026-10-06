import math
import unittest

from qa_engine.ai.decision import Choice, ChoiceAnswer, DecisionError, Noul, NoulAnswer, Score, ScoreAnswer
from qa_engine.ai.decision_providers import (
    CascadeDecisionProvider,
    LogprobDecisionProvider,
    SystemOneProvider,
    build_messages,
)
from qa_engine.ai.decision_tasks import DEFAULT_RULES, RuleDecisionProvider, header_question


def logprob_response(probs: dict[str, float], prompt_tokens: int = 10) -> dict:
    top = [{"token": token, "logprob": math.log(p)} for token, p in probs.items()]
    return {
        "choices": [{"logprobs": {"content": [{"token": top[0]["token"], "logprob": top[0]["logprob"],
                                               "top_logprobs": top}]}}],
        "usage": {"prompt_tokens": prompt_tokens},
    }


class SystemOneProviderTest(unittest.TestCase):
    def test_parses_typesafe_response(self):
        sent = {}

        def transport(url, payload, headers, timeout):
            sent.update(url=url, payload=payload, headers=headers)
            return {
                "model": "laya:en",
                "answers": {
                    "intent": {"type": "choice", "choice": "invoice", "confidence": 0.9,
                               "probabilities": {"invoice": 0.933, "refund": 0.021, "other": 0.046}},
                    "urgency": {"type": "score", "score": 1.2, "confidence": 0.34,
                                "probabilities": {"0": 0.12, "1": 0.56, "2": 0.32}},
                    "billing": {"type": "noul", "noul": 0.96},
                },
                "usage": {"input_tokens": 71, "output_tokens": 0},
            }

        provider = SystemOneProvider("http://127.0.0.1:11435/", "laya", api_key="k", transport=transport)
        result = provider.decide("Can I get an invoice?", {
            "intent": Choice("What?", {"invoice": "Needs an invoice", "refund": "Money back", "other": "Else"}),
            "urgency": Score("How urgent?", ["Can wait", "This week", "Today"]),
            "billing": Noul("About billing?"),
        })
        self.assertEqual(sent["url"], "http://127.0.0.1:11435/v1/systemone")
        self.assertEqual(sent["headers"], {"Authorization": "Bearer k"})
        self.assertEqual(sent["payload"]["questions"]["urgency"]["criteria"], ["Can wait", "This week", "Today"])
        self.assertEqual(result.answers["intent"].choice, "invoice")
        self.assertAlmostEqual(result.answers["intent"].confidence, 0.933 - 0.046)
        self.assertAlmostEqual(result.answers["urgency"].score, 1.2)
        self.assertAlmostEqual(result.answers["billing"].noul, 0.96)

    def test_error_response_raises(self):
        provider = SystemOneProvider("http://x", "laya:xl",
                                     transport=lambda *a: {"error": "not found", "code": "MODEL_NOT_FOUND"})
        with self.assertRaises(DecisionError):
            provider.decide("s", {"q": Noul("?")})


class LogprobProviderTest(unittest.TestCase):
    def test_choice_merges_label_variants_and_normalizes(self):
        provider = LogprobDecisionProvider(
            "http://127.0.0.1:8080/v1", "m",
            transport=lambda *a: logprob_response({"B": 0.6, " B": 0.1, "A": 0.2, "x": 0.1}),
        )
        answer = provider.decide("state", {"q": Choice("?", {"a": "", "b": ""})}).answers["q"]
        self.assertIsInstance(answer, ChoiceAnswer)
        self.assertEqual(answer.choice, "b")
        self.assertAlmostEqual(answer.probabilities["b"], 0.7 / 0.9)

    def test_noul_and_score(self):
        provider = LogprobDecisionProvider("http://x/v1", "m",
                                           transport=lambda *a: logprob_response({"A": 0.8, "B": 0.2}))
        result = provider.decide("s", {"n": Noul("?"), "s": Score("?", ["low", "high"])})
        self.assertIsInstance(result.answers["n"], NoulAnswer)
        self.assertAlmostEqual(result.answers["n"].noul, 0.8)
        self.assertIsInstance(result.answers["s"], ScoreAnswer)
        self.assertAlmostEqual(result.answers["s"].score, 0.2)
        self.assertEqual(result.usage["input_tokens"], 20)

    def test_no_label_in_candidates_raises(self):
        provider = LogprobDecisionProvider("http://x/v1", "m",
                                           transport=lambda *a: logprob_response({"<think>": 0.9}))
        with self.assertRaises(DecisionError):
            provider.decide("s", {"n": Noul("?")})

    def test_state_comes_before_question(self):
        messages, labels = build_messages("STATE", Choice("QUESTION", {"x": "説明"}))
        user = messages[1]["content"]
        self.assertLess(user.index("STATE"), user.index("QUESTION"))
        self.assertEqual(labels, {"A": "x"})


class CascadeTest(unittest.TestCase):
    def test_only_unsure_questions_go_to_next_stage(self):
        asked = []

        def transport(url, payload, headers, timeout):
            asked.append(payload["messages"][1]["content"])
            return logprob_response({"A": 0.9, "B": 0.1})

        llm = LogprobDecisionProvider("http://x/v1", "m", transport=transport)
        cascade = CascadeDecisionProvider([(RuleDecisionProvider(DEFAULT_RULES), 0.6), (llm, 0.0)])
        result = cascade.decide(
            {"記述A": "CSV出力で文字化けが発生する", "記述B": "CSV出力で文字化けが発生する"},
            {"duplicate": Noul("同じ?"), "cause": Choice("原因?", {"実装誤り": "", "設計誤り": ""})},
        )
        self.assertEqual(result.answered_by["duplicate"], "rules")  # 完全一致なのでルールで確定
        self.assertEqual(result.answered_by["cause"], "logprobs:m")  # ルールが無いので LLM へ
        self.assertEqual(len(asked), 1)
        self.assertEqual(list(result.answers), ["duplicate", "cause"])


class HeaderQuestionTest(unittest.TestCase):
    def test_candidates_skip_title_lines(self):
        lines = ["障害一覧", "", "ID,日付,現象", "1,2026/01/01,落ちる", "2,2026/01/02,遅い"]
        state, questions = header_question(lines)
        self.assertEqual(list(questions["header"].criteria), ["2", "3", "4"])
        self.assertIn("障害一覧", state)
        answer = RuleDecisionProvider(DEFAULT_RULES).decide(state, questions).answers["header"]
        self.assertEqual(answer.choice, "2")


if __name__ == "__main__":
    unittest.main()
