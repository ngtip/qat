"""定量分析: チェック結果や統計値の集計。"""


def duplicate_ratio(duplicate_check_results: list[dict], total_rows: int) -> float:
    if total_rows == 0:
        return 0.0
    flagged = sum(1 for r in duplicate_check_results if r.get("duplicate_matches"))
    return flagged / total_rows
