"""分析結果(構造化データ)を表示用の表に整える。分析ロジックとは分離し、表示形式の変更で再分析が要らないようにする。"""

import pandas as pd

from qa_engine.ai.providers import PROVIDER_LABELS
from qa_engine.ai.tasks import COLUMN_SUGGESTION, HEADER_DETECTION, WORD_MINING

SCORE_LABELS = {
    "duplicate_ratio": "重複候補の割合",
    "major_ratio": "重大(S/A)の割合",
    "word_weight_avg": "重み付き語スコア平均",
    "overall_score": "総合品質スコア(暫定)",
}
STEP_LABELS = {t.key: t.label for t in (HEADER_DETECTION, COLUMN_SUGGESTION, WORD_MINING)}


def format_scores_for_display(scores: list[dict]) -> list[dict]:
    return [
        {"項目": SCORE_LABELS.get(s["metric_name"], s["metric_name"]), "値": s["value"]}
        for s in scores
        if s.get("row_id") is None
    ]


def interactions_frame(interactions: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日時(UTC)": i["created_at"],
                "工程": STEP_LABELS.get(i["step"], i["step"]),
                "呼び先": PROVIDER_LABELS.get(i["provider"], i["provider"]),
                "送信したプロンプト": i["prompt"],
                "AIの応答": i["response"],
            }
            for i in interactions
        ],
        columns=["日時(UTC)", "工程", "呼び先", "送信したプロンプト", "AIの応答"],
    )
