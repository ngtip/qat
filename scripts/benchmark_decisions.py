"""判断モデル(Jev型)の精度と速度を、ダミーデータで測るベンチマーク。

正解付きのケースは data/samples/bug_tickets_demo.csv(架空データ)から作る。
実データは使わないので、外部API(Jevクラウド)に向けて測っても問題ない。

使い方(プロジェクトルートで実行):
  # ルールだけ(サーバ不要。比較の基準)
  .venv/Scripts/python scripts/benchmark_decisions.py --target rules

  # Ollaya(TypeSafe互換)
  .venv/Scripts/python scripts/benchmark_decisions.py --target systemone \
      --base-url http://127.0.0.1:11435 --model winnow:e4b

  # llama-server などの OpenAI 互換 API(logprobs)。Qwen3 系は --no-think
  .venv/Scripts/python scripts/benchmark_decisions.py --target logprobs \
      --base-url http://127.0.0.1:8080/v1 --model qwen3-4b --no-think

  # ルールで答え、確信度 0.6 未満だけ LLM に回す(多段)
  ... --target logprobs ... --cascade --threshold 0.6

結果は表で表示し、ケースごとの記録を data/bench/ に JSON で保存する。
"""

import argparse
import csv
import io
import json
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qa_engine.ai.decision import (  # noqa: E402
    Choice,
    ChoiceAnswer,
    DecisionError,
    DecisionProvider,
    NoulAnswer,
    Question,
)
from qa_engine.ai.decision_providers import (  # noqa: E402
    CascadeDecisionProvider,
    LogprobDecisionProvider,
    SystemOneProvider,
)
from qa_engine.ai.decision_tasks import (  # noqa: E402
    DEFAULT_RULES,
    DUPLICATE_QUESTION,
    RuleDecisionProvider,
    column_questions,
    column_state,
    duplicate_state,
    header_question,
)

DEMO_CSV = ROOT / "data" / "samples" / "bug_tickets_demo.csv"
OUT_DIR = ROOT / "data" / "bench"
SEED = 20261006


@dataclass
class Case:
    task: str
    case_id: str
    state: str | dict[str, Any]
    questions: dict[str, Question]
    expected: dict[str, str | bool]  # 質問キー -> 正解(Choice はキー、Noul は bool)


# --- 正解付きケースの作成 ---------------------------------------------------------

COLUMN_TRUTH = {
    "障害ID": ("id", False),
    "起票日": ("date", True),
    "発見工程": ("category", True),
    "機能": ("category", True),
    "重要度": ("severity", True),
    "現象": ("free_text", True),
    "原因区分": ("category", True),
    "原因詳細": ("free_text", True),
    "対策": ("free_text", True),
    "担当者": ("person", False),
    "ステータス": ("category", True),
    "対応工数h": ("numeric", True),
}

CAUSE_CRITERIA = {
    "実装誤り": "設計どおりに実装されていなかった",
    "設計誤り": "設計そのものに考慮漏れや誤りがあった",
    "仕様漏れ": "仕様書に必要な記載がなかった",
    "環境・設定": "サーバや接続先などの設定の誤り",
    "データ不備": "投入・移行したデータの誤り",
    "テスト漏れ": "テストで確認すべきパターンが漏れていた",
}


def load_demo() -> tuple[str, list[str], list[dict]]:
    text = DEMO_CSV.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    header_index = 2  # 表題・注記の2行のあとがヘッダ(generate_demo_data.py の出力形式)
    records = list(csv.reader(io.StringIO("\n".join(lines[header_index:]))))
    header = records[0]
    rows = [dict(zip(header, r)) for r in records[1:] if any(c.strip() for c in r)]
    return text, header, rows


def header_cases(text: str) -> list[Case]:
    lines = text.splitlines()
    body = lines[2:]  # ヘッダ以降
    as_tab = ["\t".join(next(csv.reader([line]))) for line in body]
    variants = [
        ("original", lines, 2),
        ("no_preamble", body, 0),
        ("tab_one_title", ["障害一覧(タブ区切り)"] + as_tab, 1),
        ("blank_and_notes", ["障害管理台帳", "", "※架空データ", "", ""] + body, 5),
        # 表題行がカンマで2列に割れてしまう(ヘッダと紛らわしい)ケース
        ("comma_title", ["出力日時: 2026/10/01 09:00,出力者: 品質管理チーム", ""] + body, 2),
        ("kv_preamble", ["システム名,受注管理システム", "対象期間,2026/08/01〜2026/09/30", ""] + body, 3),
    ]
    cases = []
    for name, variant, expected in variants:
        state, questions = header_question(variant)
        cases.append(Case("header", name, state, questions, {"header": str(expected)}))
    return cases


def column_cases(header: list[str], rows: list[dict]) -> list[Case]:
    cases = []
    for column in header:
        role, use = COLUMN_TRUTH[column]
        values = [r[column] for r in rows]
        cases.append(Case("column", column, column_state(column, values), column_questions(),
                          {"role": role, "use": use}))
    return cases


def cause_cases(rows: list[dict]) -> list[Case]:
    seen, cases = set(), []
    question = Choice("この不具合の原因区分はどれか", CAUSE_CRITERIA)
    for r in rows:
        key = (r["現象"], r["原因詳細"])
        if not r["原因詳細"] or key in seen:
            continue
        seen.add(key)
        state = {"現象": r["現象"], "原因詳細": r["原因詳細"]}
        cases.append(Case("cause", r["障害ID"], state, {"cause": question}, {"cause": r["原因区分"]}))
    return cases


def duplicate_cases(rows: list[dict], rng: random.Random, per_side: int = 20) -> list[Case]:
    """同じ原因詳細の組 = 同じ不具合(正例)、同じ機能で原因詳細が違う組 = 別の不具合(負例)。"""
    by_issue: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        if r["原因詳細"]:
            by_issue.setdefault((r["機能"], r["原因詳細"]), set()).add(r["現象"])
    issues = sorted(by_issue)
    positives = [(a, b) for k in issues for a in sorted(by_issue[k]) for b in sorted(by_issue[k]) if a < b]
    negatives = [(a, b) for i, k1 in enumerate(issues) for k2 in issues[i + 1:] if k1[0] == k2[0]
                 for a in sorted(by_issue[k1])[:1] for b in sorted(by_issue[k2])[:1]]
    rng.shuffle(negatives)
    pairs = [(p, True) for p in positives[:per_side]] + [(n, False) for n in negatives[:per_side]]
    return [Case("duplicate", f"dup{i:02d}", duplicate_state(a, b), {"duplicate": DUPLICATE_QUESTION},
                 {"duplicate": same}) for i, ((a, b), same) in enumerate(pairs)]


def build_cases(tasks: list[str]) -> list[Case]:
    text, header, rows = load_demo()
    builders = {
        "header": lambda: header_cases(text),
        "column": lambda: column_cases(header, rows),
        "cause": lambda: cause_cases(rows),
        "duplicate": lambda: duplicate_cases(rows, random.Random(SEED)),
    }
    return [case for task in tasks for case in builders[task]()]


# --- 実行と集計 ------------------------------------------------------------------

def score_answer(answer, expected) -> tuple[bool, float]:
    """(正解したか, 正解に付けた確率)"""
    if isinstance(answer, NoulAnswer):
        p = answer.noul if expected else 1 - answer.noul
        return p > 0.5, p
    if isinstance(answer, ChoiceAnswer):
        return answer.choice == expected, answer.probabilities.get(str(expected), 0.0)
    return False, 0.0


def run(provider: DecisionProvider, cases: list[Case]) -> list[dict]:
    records = []
    for case in cases:
        started = time.perf_counter()
        try:
            result = provider.decide(case.state, case.questions)
            error = None
        except DecisionError as e:
            result, error = None, str(e)
        seconds = time.perf_counter() - started
        for key, expected in case.expected.items():
            record = {"task": case.task, "case": case.case_id, "question": key,
                      "expected": expected, "seconds": round(seconds, 4), "error": error}
            if result and key in result.answers:
                answer = result.answers[key]
                correct, p_true = score_answer(answer, expected)
                record.update({
                    "answer": answer.choice if isinstance(answer, ChoiceAnswer) else round(answer.noul, 4),
                    "correct": correct,
                    "p_expected": round(p_true, 4),
                    "confidence": round(answer.confidence, 4),
                    "answered_by": result.answered_by.get(key, provider.name),
                })
            else:
                record.update({"answer": None, "correct": False, "p_expected": 0.0, "confidence": 0.0,
                               "answered_by": None})
            records.append(record)
        print(".", end="", flush=True)
    print()
    return records


def summarize(records: list[dict]) -> list[dict]:
    rows = []
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        groups.setdefault((r["task"], r["question"]), []).append(r)
    for (task, question), items in groups.items():
        seconds = sorted(r["seconds"] for r in items)
        by_stage: dict[str, int] = {}
        for r in items:
            by_stage[r["answered_by"] or "error"] = by_stage.get(r["answered_by"] or "error", 0) + 1
        rows.append({
            "task": task,
            "question": question,
            "n": len(items),
            "accuracy": sum(r["correct"] for r in items) / len(items),
            # 正解に付けた確率の平均(1に近いほど、自信を持って正解している)
            "mean_p_expected": statistics.mean(r["p_expected"] for r in items),
            "mean_seconds": statistics.mean(seconds),
            "p95_seconds": seconds[min(len(seconds) - 1, int(len(seconds) * 0.95))],
            "errors": sum(1 for r in items if r["error"]),
            "answered_by": by_stage,
        })
    return rows


def print_table(rows: list[dict]) -> None:
    print("| タスク | 質問 | 件数 | 正解率 | 正解への確率 | 平均秒 | p95秒 | エラー | 回答元 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        stages = ", ".join(f"{k}={v}" for k, v in r["answered_by"].items())
        print(f"| {r['task']} | {r['question']} | {r['n']} | {r['accuracy']:.1%} | {r['mean_p_expected']:.3f} "
              f"| {r['mean_seconds']:.3f} | {r['p95_seconds']:.3f} | {r['errors']} | {stages} |")


def build_provider(args: argparse.Namespace) -> DecisionProvider:
    rules = RuleDecisionProvider(DEFAULT_RULES)
    if args.target == "rules":
        return rules
    if args.target == "systemone":
        llm = SystemOneProvider(args.base_url, args.model, os.environ.get(args.api_key_env))
    else:
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if args.no_think else {}
        llm = LogprobDecisionProvider(args.base_url, args.model, os.environ.get(args.api_key_env),
                                      extra_body=extra, concurrency=args.concurrency)
    return CascadeDecisionProvider([(rules, args.threshold), (llm, 0.0)]) if args.cascade else llm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=["rules", "systemone", "logprobs"], default="rules")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env", default="TYPESAFE_API_KEY", help="APIキーを読む環境変数名")
    parser.add_argument("--no-think", action="store_true", help="思考モードを切る(llama-server の Qwen3 系)")
    parser.add_argument("--concurrency", type=int, default=1, help="同じ状態への質問を並列に送る数")
    parser.add_argument("--cascade", action="store_true", help="ルールで先に答え、迷ったものだけLLMへ")
    parser.add_argument("--threshold", type=float, default=0.6, help="多段のとき、ルールの回答を採用する確信度")
    parser.add_argument("--tasks", default="header,column,cause,duplicate")
    parser.add_argument("--label", help="結果ファイル名に付ける名前(例: winnow-e4b-cpu)")
    args = parser.parse_args()
    if args.target != "rules" and not (args.base_url and args.model):
        parser.error("--target が rules 以外のときは --base-url と --model が必要です")

    provider = build_provider(args)
    cases = build_cases([t.strip() for t in args.tasks.split(",") if t.strip()])
    print(f"{provider.name} で {len(cases)} ケースを実行します")
    started = time.perf_counter()
    records = run(provider, cases)
    total = time.perf_counter() - started
    summary = summarize(records)
    print_table(summary)
    print(f"\n合計 {total:.1f} 秒")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    label = args.label or provider.name.replace(":", "-").replace(" > ", "+").replace("/", "-")
    path = OUT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{label}.json"
    path.write_text(json.dumps({
        "provider": provider.name,
        "args": {k: v for k, v in vars(args).items() if k != "api_key_env"},
        "total_seconds": round(total, 2),
        "summary": summary,
        "records": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"結果: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
