"""DBから集めた結果を、画面とExcelで共通に使うレポートの形にまとめる。"""

from dataclasses import dataclass, field

import pandas as pd

from qa_engine.analysis.qualitative import weighted_average
from qa_engine.analysis.quantitative import (
    category_counts,
    duplicate_ratio,
    major_ratio,
    numeric_mean,
    severity_crosstab,
    weekly_trend,
)
from qa_engine.analysis.scoring import attention_ranking, attention_tickets, naive_calculate_scores
from qa_engine.report.formatter import format_scores_for_display, interactions_frame

NOTE = "集計・スコアの式は暫定ロジックであり、精度は未検証。"


@dataclass
class Report:
    kpis: list[tuple[str, str]]
    scores: list[dict]
    category_counts: dict[str, pd.DataFrame]
    crosstabs: dict[str, pd.DataFrame]
    trend: pd.DataFrame | None
    ranking_col: str | None
    ranking: pd.DataFrame | None
    attention: pd.DataFrame
    duplicates: pd.DataFrame
    words: pd.DataFrame
    interactions: pd.DataFrame
    columns_used: dict[str, list[str]] = field(default_factory=dict)

    def summary_frame(self) -> pd.DataFrame:
        rows = [{"項目": label, "値": value} for label, value in self.kpis]
        rows += format_scores_for_display([s for s in self.scores if s["metric_name"] == "overall_score"])
        rows += [{"項目": f"使用した列({role})", "値": "、".join(cols)} for role, cols in self.columns_used.items()]
        rows.append({"項目": "注記", "値": NOTE})
        return pd.DataFrame(rows)

    def sheets(self) -> dict[str, pd.DataFrame]:
        def stacked(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
            parts = [t.rename(columns={col: "値"}).assign(分類列=col) for col, t in tables.items()]
            if not parts:
                return pd.DataFrame()
            merged = pd.concat(parts, ignore_index=True)
            return merged[["分類列", *[c for c in merged.columns if c != "分類列"]]]

        sheets = {"サマリ": self.summary_frame(), "分類別件数": stacked(self.category_counts)}
        if self.crosstabs:
            sheets["重要度クロス"] = stacked(self.crosstabs).fillna(0)
        if self.trend is not None:
            sheets["週次推移"] = self.trend
        if self.ranking is not None:
            sheets["要注意度"] = self.ranking
        sheets.update({
            "要注目障害": self.attention,
            "重複候補": self.duplicates,
            "重要語と重み": self.words,
            "AI処理ログ": self.interactions,
        })
        return sheets


def _first(roles: dict[str, str], columns: list[str], role: str) -> str | None:
    return next((c for c in columns if roles.get(c) == role), None)


def build_report(
    rows: list[dict],
    roles: dict[str, str],
    selected: list[str],
    duplicate_results: list[dict],
    words: list[dict],
    interactions: list[dict],
    ranking_col: str | None = None,
) -> Report:
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("id", "row_index")} for r in rows])
    date_col = _first(roles, selected, "date")
    severity_col = _first(roles, selected, "severity")
    numeric_col = _first(roles, selected, "numeric")
    id_col = _first(roles, list(roles), "id")
    category_cols = [c for c in selected if roles.get(c) == "category"]
    text_cols = [c for c in selected if roles.get(c) == "free_text"]
    if ranking_col not in category_cols:
        ranking_col = category_cols[0] if category_cols else None

    weights = {
        w["term"]: w["user_weight"] if w["user_weight"] is not None else w["ai_score"] for w in words
    }
    dup_ratio = duplicate_ratio(duplicate_results, len(rows))
    word_avg = weighted_average([w["frequency"] for w in words], list(weights.values()))
    scores = naive_calculate_scores(dup_ratio, word_avg)

    attention = attention_tickets(df, id_col, severity_col, text_cols, weights)
    flagged = sum(1 for r in duplicate_results if r.get("duplicate_matches"))
    kpis = [("対象件数", f"{len(df)}件"), ("重複候補がある行", f"{flagged}件")]
    if severity_col:
        ratio = major_ratio(df, severity_col)
        scores.append({"metric_name": "major_ratio", "value": round(ratio, 3)})
        kpis.insert(1, ("重大(S/A)の割合", f"{ratio:.0%}"))
    if numeric_col and (mean := numeric_mean(df, numeric_col)) is not None:
        kpis.append((f"平均{numeric_col}", f"{mean:.1f}"))
    kpis.append(("要注目障害", f"{len(attention)}件"))

    rows_by_id = {r["id"]: r for r in rows}
    index_to_label = {r["row_index"]: (r.get(id_col) if id_col else r["row_index"]) for r in rows}
    duplicates = pd.DataFrame(
        [
            {
                "ID": index_to_label[rows_by_id[d["row_id"]]["row_index"]],
                **{c: rows_by_id[d["row_id"]].get(c, "") for c in (text_cols or selected)},
                "重複候補": "、".join(str(index_to_label[m["row_index"]]) for m in d["duplicate_matches"]),
                "最大類似度": max(m["similarity"] for m in d["duplicate_matches"]),
            }
            for d in duplicate_results
            if d.get("duplicate_matches")
        ]
    )

    return Report(
        kpis=kpis,
        scores=scores,
        category_counts={c: category_counts(df, c) for c in category_cols},
        crosstabs={c: severity_crosstab(df, c, severity_col) for c in category_cols} if severity_col else {},
        trend=weekly_trend(df, date_col, severity_col) if date_col else None,
        ranking_col=ranking_col,
        ranking=attention_ranking(df, ranking_col, severity_col, text_cols, weights) if ranking_col else None,
        attention=attention,
        duplicates=duplicates,
        words=pd.DataFrame(
            [
                {"語句": w["term"], "カテゴリ": w["category"] or "", "出現回数": w["frequency"],
                 "AI重要度": w["ai_score"], "重み": weights[w["term"]]}
                for w in words
            ],
            columns=["語句", "カテゴリ", "出現回数", "AI重要度", "重み"],
        ),
        interactions=interactions_frame(interactions),
        columns_used={
            label: cols
            for label, cols in (
                ("日付", [date_col] if date_col else []),
                ("重要度", [severity_col] if severity_col else []),
                ("分類", category_cols),
                ("自由記述", text_cols),
            )
            if cols
        },
    )
