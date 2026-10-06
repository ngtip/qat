"""スコアリング(暫定ロジック)。品質指標が固まったら置き換える。

中長期分析(蓄積データを跨いだ分析)は、storage側に同一スキーマでセッションが積み上がっている前提で将来ここに追加する。
"""

import pandas as pd

from qa_engine.analysis.quantitative import BLANK, MAJOR_THRESHOLD, severity_weight

HIGH_WEIGHT = 0.7


def row_texts(df: pd.DataFrame, text_cols: list[str]) -> list[str]:
    if not text_cols:
        return [""] * len(df)
    return df[text_cols].fillna("").astype(str).agg(" / ".join, axis=1).tolist()


def term_hits(texts: list[str], weights: dict[str, float], threshold: float = HIGH_WEIGHT) -> list[list[str]]:
    """各行の本文に含まれる、重みが閾値以上の語。"""
    important = [t for t, w in weights.items() if w >= threshold]
    return [[t for t in important if t in text] for text in texts]


def _severity_series(df: pd.DataFrame, severity_col: str | None) -> pd.Series:
    if not severity_col:
        return pd.Series(0, index=df.index)
    return df[severity_col].map(severity_weight)


def attention_ranking(
    df: pd.DataFrame,
    group_col: str,
    severity_col: str | None,
    text_cols: list[str],
    weights: dict[str, float],
) -> pd.DataFrame:
    """分類ごとの要注意度(0〜100)。重要度の重みの合計と、重要語の当たり(重み付き)の合計から出す。"""
    severity = _severity_series(df, severity_col)
    hits = term_hits(row_texts(df, text_cols), weights)
    work = pd.DataFrame({
        group_col: df[group_col].fillna("").astype(str).str.strip().replace("", BLANK),
        "sev": severity,
        "major": severity >= MAJOR_THRESHOLD,
        "hit": [sum(weights[t] for t in h) for h in hits],
    })
    grouped = work.groupby(group_col).agg(
        件数=("sev", "size"), 重大件数=("major", "sum"), 重要度合計=("sev", "sum"), 重要語ヒット=("hit", "sum"),
    )
    raw = grouped["重要度合計"] + grouped["重要語ヒット"] * 2
    grouped["要注意度"] = (raw / raw.max() * 100).round(0) if raw.max() > 0 else 0
    grouped["重要語ヒット"] = grouped["重要語ヒット"].round(1)
    return grouped.sort_values("要注意度", ascending=False).reset_index()


def attention_tickets(
    df: pd.DataFrame,
    id_col: str | None,
    severity_col: str | None,
    text_cols: list[str],
    weights: dict[str, float],
) -> pd.DataFrame:
    """重大(重要度の重みが閾値以上)で、かつ重みの高い語を含む障害。"""
    severity = _severity_series(df, severity_col)
    texts = row_texts(df, text_cols)
    hits = term_hits(texts, weights)
    records = []
    for i, (sev, terms) in enumerate(zip(severity, hits)):
        if sev < MAJOR_THRESHOLD or not terms:
            continue
        record = {"ID": df.iloc[i][id_col]} if id_col else {"行": i}
        if severity_col:
            record[severity_col] = df.iloc[i][severity_col]
        record["内容"] = texts[i]
        record["該当した重要語"] = "、".join(terms)
        record["注目スコア"] = round(sev * sum(weights[t] for t in terms), 2)
        records.append(record)
    if not records:
        return pd.DataFrame(columns=["ID", "内容", "該当した重要語", "注目スコア"])
    return pd.DataFrame(records).sort_values("注目スコア", ascending=False).reset_index(drop=True)


def naive_calculate_scores(duplicate_ratio: float, word_weight_avg: float) -> list[dict]:
    """仮の総合スコア。品質分析の指標が固まったら置き換える。"""
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
