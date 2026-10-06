"""定量分析: 件数・分類別の集計・推移(暫定ロジック)。"""

import pandas as pd

SEVERITY_WEIGHTS = {
    "S": 4, "A": 3, "B": 2, "C": 1,
    "緊急": 4, "致命": 4, "重大": 3, "高": 3, "中": 2, "軽微": 1, "低": 1,
}
MAJOR_THRESHOLD = 3
BLANK = "(空欄)"


def severity_weight(value: object) -> int:
    text = str(value).strip()
    return SEVERITY_WEIGHTS.get(text, SEVERITY_WEIGHTS.get(text.upper(), 0))


def duplicate_ratio(duplicate_check_results: list[dict], total_rows: int) -> float:
    if total_rows == 0:
        return 0.0
    flagged = sum(1 for r in duplicate_check_results if r.get("duplicate_matches"))
    return flagged / total_rows


def major_ratio(df: pd.DataFrame, severity_col: str) -> float:
    if df.empty:
        return 0.0
    return float((df[severity_col].map(severity_weight) >= MAJOR_THRESHOLD).mean())


def numeric_mean(df: pd.DataFrame, column: str) -> float | None:
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _filled(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().replace("", BLANK)


def category_counts(df: pd.DataFrame, column: str) -> pd.DataFrame:
    counts = _filled(df[column]).value_counts()
    return counts.rename_axis(column).reset_index(name="件数")


def _severity_order(values) -> list:
    return sorted(values, key=lambda v: (-severity_weight(v), str(v)))


def severity_crosstab(df: pd.DataFrame, column: str, severity_col: str) -> pd.DataFrame:
    table = pd.crosstab(_filled(df[column]), _filled(df[severity_col]))
    table = table[_severity_order(table.columns)]
    table["合計"] = table.sum(axis=1)
    table = table.sort_values("合計", ascending=False)
    table.columns.name = None
    return table.rename_axis(column).reset_index()


def weekly_trend(df: pd.DataFrame, date_col: str, severity_col: str | None = None) -> pd.DataFrame:
    """週(月曜始まり)ごとの件数。重要度の列があれば重要度別に分ける。"""
    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = dates.notna()
    if not valid.any():
        return pd.DataFrame(columns=["週", "件数"])
    weeks = dates[valid].dt.to_period("W-SUN")
    full = pd.period_range(weeks.min(), weeks.max(), freq="W-SUN")
    if severity_col:
        table = pd.crosstab(weeks, _filled(df.loc[valid, severity_col]))
        table = table.reindex(full, fill_value=0)[_severity_order(table.columns)]
    else:
        table = weeks.value_counts().reindex(full, fill_value=0).to_frame("件数")
    table.index = [p.start_time.strftime("%Y/%m/%d") for p in table.index]
    table.columns.name = None
    if severity_col:
        table["件数"] = table.sum(axis=1)
    return table.rename_axis("週").reset_index()
