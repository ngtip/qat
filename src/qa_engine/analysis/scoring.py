"""定量・定性分析の結果を統合し、品質スコアを算出する。

開発初期は短期分析(取込データのみ)を対象とする。中長期分析(蓄積データを跨いだ分析)は
storage側に同一スキーマでセッションが積み上がっている前提で、将来ここに追加する。
"""


def naive_calculate_scores(duplicate_ratio: float, word_weight_avg: float) -> list[dict]:
    """仮の合成式。品質分析の指標が固まったら置き換える。"""
    overall = (1 - duplicate_ratio) * 100 * (0.5 + 0.5 * word_weight_avg)
    return [
        {"metric_name": "duplicate_ratio", "value": round(duplicate_ratio, 3)},
        {"metric_name": "word_weight_avg", "value": round(word_weight_avg, 3)},
        {
            "metric_name": "overall_score",
            "value": round(overall, 1),
            "detail": {"formula": "(1 - duplicate_ratio) * 100 * (0.5 + 0.5 * word_weight_avg)"},
        },
    ]
