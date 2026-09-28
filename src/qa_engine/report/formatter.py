"""分析結果(構造化データ)からレポート表示形式への変換。

分析ロジック(analysis/)とは分離し、出力形式の変更が分析の再実行を必要としないようにする。
"""

_LABELS = {
    "duplicate_ratio": "重複行の割合",
    "word_weight_avg": "重み付き語スコア平均",
    "overall_score": "総合品質スコア(仮)",
}


def format_scores_for_display(scores: list[dict]) -> list[dict]:
    return [
        {"項目": _LABELS.get(s["metric_name"], s["metric_name"]), "値": s["value"]}
        for s in scores
        if s.get("row_id") is None
    ]
